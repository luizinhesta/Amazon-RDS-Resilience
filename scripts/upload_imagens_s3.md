# Upload das imagens dos produtos para o Amazon S3

> **Projeto 01 — Fase 4 (Imagens no S3) · Tarefa 24**
> **Requisitos atendidos:** 6 (migrar imagens para o S3; banco guarda só a referência), 11 (menor privilégio — IAM Role na EC2 em vez de credenciais hardcode), 12 (ATENÇÃO DE CUSTO do S3), 14 (guia passo a passo em Português-Brasil com validação e resultado esperado).

## Contexto

Até a Fase 3, as imagens dos produtos (`headset.svg`, `monitor.svg`, `mouse.svg`, `notebook.svg`, `teclado.svg` e o `sem-imagem.svg`) eram servidas **localmente pela própria EC2**, a partir de `app/static/images/`. Isso mantinha um acoplamento indesejado: os arquivos dependiam da instância — se a EC2 fosse trocada, recriada ou perdida, as imagens iriam junto.

Nesta tarefa movemos os arquivos para o **Amazon S3**. O banco continua guardando apenas a **referência** (o nome/chave do arquivo, ex.: `notebook.svg`) na coluna `produtos.imagem` — **nunca** o binário da imagem (Requisito 6.4). Quem monta a URL final é a função `url_imagem()` de `app/storage.py`: com `STORAGE_MODE=s3`, ela devolve `https://<bucket>.s3.<regiao>.amazonaws.com/<referencia>`. Ou seja, **nada muda no banco nem no código** — troca-se apenas a configuração (`.env`) e faz-se o upload dos mesmos arquivos.

A **criação do bucket** e a **ativação do `STORAGE_MODE=s3`** estão detalhadas no `IMPLANTACAO.md`, **Passo 4.1**. Este script cobre a parte operacional do **upload dos arquivos** a partir da EC2, usando a **AWS CLI** com uma **IAM Role** anexada à instância (sem credenciais no código ou no disco).

- **Onde tudo é executado:** **dentro da EC2, via SSH**. Conecte-se antes de começar:
  ```bash
  ssh -i aws-database-lab-key.pem ec2-user@IP_PUBLICO_DA_EC2
  ```
- **Nome do bucket:** definido no `IMPLANTACAO.md` (Passo 4.1). Nos comandos abaixo, substitua `<NOME-DO-BUCKET>` pelo valor real (ex.: `aws-database-lab-imagens-SEU_SUFIXO`).
- **Região:** `us-east-1` (mesma da EC2 e do RDS).

---

## Por que IAM Role e não credenciais fixas (Requisito 11 — menor privilégio)

Existem duas formas de a AWS CLI autenticar na EC2:

| Forma | Como funciona | Recomendação |
|---|---|---|
| **IAM Role anexada à EC2** (recomendada) | A instância recebe **credenciais temporárias e rotacionadas automaticamente** pelo serviço de metadados. Nenhuma chave fica salva em disco. | ✅ **Use esta.** É o padrão de segurança da AWS. |
| **Chaves de acesso fixas** (`aws configure` com `Access Key`/`Secret Key`) | Uma chave de longa duração é gravada em `~/.aws/credentials`. | ❌ **Evite.** Se a chave vazar (ex.: commit acidental, print), o acesso continua válido até ser revogado. |

Com a IAM Role, se a EC2 for comprometida a exposição é **limitada e temporária**, e nunca há segredo para vazar no Git — coerente com o Requisito 11.4/11.5 (credenciais fora do código).

### Política de menor privilégio da Role

A Role da EC2 precisa apenas de **`PutObject`** (enviar as imagens) e **`GetObject`** (a aplicação/validação ler os objetos), restrita ao **bucket deste laboratório**. Nada de `s3:*` nem acesso a todos os buckets da conta. Exemplo de política (JSON) a anexar à Role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ImagensLabPutGet",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::<NOME-DO-BUCKET>/*"
    },
    {
      "Sid": "ImagensLabListBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<NOME-DO-BUCKET>"
    }
  ]
}
```

> **Observação:** a permissão `s3:ListBucket` (no ARN do **bucket**, sem `/*`) é opcional, mas ajuda o `aws s3 sync` a comparar o que já existe. As permissões de escrita/leitura de objeto (`PutObject`/`GetObject`) usam o ARN com `/*` (nível de **objeto**). O guia de **criação e anexação da Role** (`ec2-imagens-s3-role`) está no `IMPLANTACAO.md`, Passo 4.1.

---

## Pré-requisitos

1. **Bucket criado** conforme o `IMPLANTACAO.md` (Passo 4.1), na região `us-east-1`.
2. **IAM Role** com a política acima **anexada à EC2** (Passo 4.1). Valide que a Role está ativa na instância:
   ```bash
   aws sts get-caller-identity
   ```
   - **Resultado esperado:** um JSON com `Account`, `UserId` e um `Arn` do tipo `.../assumed-role/ec2-imagens-s3-role/...` — comprovando que a CLI está usando a **Role da instância** (e não chaves fixas).
3. **AWS CLI instalada** na EC2. O Amazon Linux 2023 já traz a CLI v2; se faltar:
   ```bash
   sudo dnf install -y awscli
   aws --version
   ```
4. Arquivos de imagem presentes na EC2, em `/opt/aws-database-lab/static/images/` (chegaram junto com o código no deploy da Fase 0).

---

## Passo 1 — Conferir os arquivos que serão enviados

- **Comando (na EC2):**
  ```bash
  cd /opt/aws-database-lab
  ls -1 static/images/
  ```
- **O que faz:** lista os arquivos de imagem locais que serão enviados ao bucket.
- **Por que executar:** garante que os nomes conferem com as referências gravadas em `produtos.imagem` (ex.: `notebook.svg`). O objeto no S3 terá **a mesma chave** (nome), então a referência do banco continua válida sem nenhuma alteração.
- **Resultado esperado:**
  ```text
  headset.svg
  monitor.svg
  mouse.svg
  notebook.svg
  sem-imagem.svg
  teclado.svg
  ```

---

## Passo 2 — Enviar as imagens para o S3

Você pode enviar **um arquivo por vez** (`aws s3 cp`) ou **a pasta inteira de uma vez** (`aws s3 sync`). O `sync` é o recomendado por ser idempotente (só envia o que mudou).

### Opção A — `aws s3 sync` (recomendada)

- **Comando:**
  ```bash
  aws s3 sync static/images/ s3://<NOME-DO-BUCKET>/ \
    --exclude "*" \
    --include "*.svg" \
    --content-type "image/svg+xml"
  ```
  - **O que cada parte faz:**
    - `sync static/images/ s3://<NOME-DO-BUCKET>/`: copia o conteúdo da pasta local para a **raiz** do bucket (as chaves ficam `notebook.svg`, `mouse.svg`, ...). Assim a URL montada por `storage.py` (`https://<bucket>.s3.us-east-1.amazonaws.com/notebook.svg`) bate exatamente com a referência do banco.
    - `--exclude "*" --include "*.svg"`: envia **apenas** os arquivos `.svg` (evita subir qualquer arquivo extra que apareça na pasta).
    - `--content-type "image/svg+xml"`: define o tipo MIME correto, para o navegador **renderizar** o SVG como imagem (sem isso, o S3 pode servir como `binary/octet-stream` e o navegador oferecer download em vez de exibir).
  - **Por que executar:** publica os mesmos arquivos no S3, encerrando a dependência da EC2 para servir imagens (Requisito 6.2/6.5).
  - **Resultado esperado:** linhas `upload: static/images/notebook.svg to s3://<NOME-DO-BUCKET>/notebook.svg` (uma por arquivo). Reexecutar o comando **não** reenvia nada (idempotente).

### Opção B — `aws s3 cp` (arquivo a arquivo)

> Útil para entender o comando individual ou reenviar um único arquivo.

- **Comando (exemplo com um arquivo):**
  ```bash
  aws s3 cp static/images/notebook.svg s3://<NOME-DO-BUCKET>/notebook.svg \
    --content-type "image/svg+xml"
  ```
- **Comando (todos de uma vez, com recursão):**
  ```bash
  aws s3 cp static/images/ s3://<NOME-DO-BUCKET>/ \
    --recursive \
    --exclude "*" \
    --include "*.svg" \
    --content-type "image/svg+xml"
  ```
- **Resultado esperado:** uma linha `upload:` por arquivo enviado.

---

## Passo 3 — Validar que os objetos estão no bucket

- **Comando:**
  ```bash
  aws s3 ls s3://<NOME-DO-BUCKET>/
  ```
- **O que faz:** lista os objetos na raiz do bucket.
- **Resultado esperado:** os 6 arquivos SVG aparecem, com data/hora e tamanho:
  ```text
  2025-01-01 12:00:00        612 headset.svg
  2025-01-01 12:00:00        548 monitor.svg
  2025-01-01 12:00:00        503 mouse.svg
  2025-01-01 12:00:00        731 notebook.svg
  2025-01-01 12:00:00        420 sem-imagem.svg
  2025-01-01 12:00:00        517 teclado.svg
  ```

- **Validação do acesso via URL pública** (após configurar o acesso de leitura no Passo 4.1 do `IMPLANTACAO.md`):
  ```bash
  curl -s -o /dev/null -w "%{http_code}\n" \
    https://<NOME-DO-BUCKET>.s3.us-east-1.amazonaws.com/notebook.svg
  ```
  - **Resultado esperado:** `200`. Um `403` indica que o objeto existe mas o **acesso de leitura pública** ainda não está liberado (revise o Passo 4.1 — Block Public Access + bucket policy de leitura).

---

## Passo 4 — Ativar `STORAGE_MODE=s3` e validar pela loja

A ativação na aplicação é feita no `.env` e está detalhada no `IMPLANTACAO.md` (Passo 4.1). Em resumo:

1. No `.env` da EC2, ajuste:
   ```bash
   STORAGE_MODE=s3
   S3_BUCKET=<NOME-DO-BUCKET>
   S3_REGION=us-east-1
   LAB_ARCH_VERSION=Fase 4 — Imagens no S3
   ```
2. Reinicie o serviço:
   ```bash
   sudo systemctl restart aws-database-lab
   ```
3. Abra a loja: as imagens agora carregam do S3 (URL `https://<bucket>.s3.us-east-1.amazonaws.com/...`), e o painel `/database-lab` passa a listar **Amazon S3** nos recursos. O banco continua com apenas a **referência** em `produtos.imagem`.

> **Nota importante (o banco não muda):** você **não** roda nenhum `UPDATE` em `produtos.imagem`. Os valores continuam sendo os nomes dos arquivos (`notebook.svg` etc.). A única coisa que muda é **como a URL é montada** — antes `images/notebook.svg` (servido pelo Flask), agora `https://<bucket>.s3.us-east-1.amazonaws.com/notebook.svg` (servido pelo S3). Isso comprova o Requisito 6.4: o banco guarda **só a referência**, nunca o binário.

---

## ATENÇÃO DE CUSTO — Amazon S3 (Requisito 12.1)

- **Recurso:** Amazon S3 (bucket de objetos).
- **Motivo:** armazenar e servir as imagens dos produtos de forma independente da EC2 (Requisito 6).
- **Quando começa a cobrança:** ao **armazenar objetos** (GB/mês), por **requisições** (`PUT`/`GET`) e por **transferência de dados de saída** (data transfer out) para a internet. O Free Tier oferece uma cota mensal (5 GB de armazenamento, 20.000 `GET` e 2.000 `PUT`) nos primeiros 12 meses.
- **Ordem de grandeza deste lab:** ínfima — são 6 arquivos SVG (texto, poucos KB cada). O custo tende a **centavos ou zero** dentro do Free Tier. O ponto de atenção é **conceitual** (entender o modelo de cobrança do S3), não o valor.
- **Por quanto tempo:** o bucket é reaproveitado nos Projetos 02, 03 e 04 (a aplicação continua servindo imagens do S3).
- **Quando pode ser removido:** ao final da série de laboratórios. Para excluir, é preciso **esvaziar** o bucket antes (`aws s3 rm s3://<NOME-DO-BUCKET>/ --recursive`) e então **excluir** o bucket. Consolidado na Tarefa 27 / seção "Recursos que podem ser removidos".
