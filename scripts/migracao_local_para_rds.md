# Migração do banco `loja` — MySQL local (EC2) → Amazon RDS

> **Projeto 01 — Fase 1 (RDS Single-AZ) · Tarefa 15**
> **Requisitos atendidos:** 3 (migrar o banco local para o RDS), 11 (usuário de aplicação com menor privilégio), 14 (guia passo a passo em Português-Brasil com validação e resultado esperado).

## Contexto

Na Fase 0, a aplicação e o banco `loja` rodavam **na mesma EC2** (MySQL local, acesso via `localhost`). Na Tarefa 14 criamos o **Amazon RDS MySQL Single-AZ** (instância `rds-mysql-lab`, usuário mestre `admin`, banco inicial `loja`, `sg-db-lab` liberando a porta `3306` **apenas** com origem = `sg-ec2-lab`).

Esta tarefa **move os dados** do MySQL local para o RDS. Ao final, o banco `loja` do RDS terá as tabelas e os dados de exemplo, e existirá nele um usuário de aplicação `app_loja@'%'` (a aplicação passará a apontar para o RDS na **Tarefa 16**).

- **Onde tudo é executado:** **dentro da EC2, via SSH**. Conecte-se antes de começar:
  ```bash
  ssh -i aws-database-lab-key.pem ec2-user@IP_PUBLICO_DA_EC2
  ```
- **Endpoint do RDS:** anotado na Tarefa 14 (formato `rds-mysql-lab.xxxxxxxx.us-east-1.rds.amazonaws.com`). Nos comandos abaixo, substitua `<ENDPOINT-DO-RDS>` pelo valor real.
- **Cliente MySQL na EC2:** já presente (pacote do MySQL da Fase 0). Em uma EC2 só de aplicação, instale apenas o cliente: `sudo dnf install -y mysql-community-client`.

### Duas abordagens (escolha uma)

| Abordagem | O que faz | Quando usar |
|---|---|---|
| **A — dump/restore** | Exporta o banco local com `mysqldump` e importa no RDS | Quando há **dados reais** no MySQL local que você quer preservar (o caso desta migração) |
| **B — reaplicar scripts versionados** | Roda `sql/01_schema.sql` e `sql/02_seed.sql` direto no RDS | Quando quer **reconstruir do zero** (schema + dados de exemplo), sem depender do estado do banco local |

Nas duas abordagens, o banco `loja` **já existe** no RDS (criado pela instância). Portanto **não** recriamos o database — apenas populamos suas tabelas.

---

## Pré-requisitos (comuns às duas abordagens)

1. RDS `rds-mysql-lab` em estado **Disponível**, privado, associado ao `sg-db-lab` (Tarefa 14).
2. Conectividade EC2 → RDS validada (Tarefa 14, passo 1.1.3):
   ```bash
   # deve responder "succeeded"
   nc -zv <ENDPOINT-DO-RDS> 3306
   ```
   Se travar/der timeout, o problema é de rede/segurança — revise o `sg-db-lab` (origem = `sg-ec2-lab`) e se RDS e EC2 estão na mesma VPC.
3. Senha do usuário mestre `admin` do RDS em mãos (definida na criação — **não** versionada).

---

## Abordagem A — Migrar os dados com `mysqldump` (dump/restore)

### Passo A.1 — Gerar o dump do banco `loja` local

- **Comando (na EC2):**
  ```bash
  cd /opt/aws-database-lab   # ou qualquer diretório de trabalho

  mysqldump \
    --single-transaction \
    --routines \
    --triggers \
    --no-create-db \
    -u root -p \
    loja > loja_dump.sql
  ```
  - **O que cada opção faz:**
    - `--single-transaction`: gera um dump **consistente** sem travar as tabelas InnoDB (faz o dump dentro de uma transação). Ideal para não interromper a aplicação durante o export.
    - `--routines`: inclui **procedures e functions** (se houver) no dump.
    - `--triggers`: inclui os **triggers** das tabelas (por padrão o mysqldump já os inclui; deixamos explícito por clareza).
    - `--no-create-db`: **não** emite `CREATE DATABASE`/`USE` para o banco. Como o RDS **já criou** o banco `loja`, não queremos recriá-lo. (O nome `loja` é passado como argumento apenas para indicar *o que* exportar.)
    - `-u root -p loja`: exporta o banco `loja` autenticando como `root` do MySQL **local** (o `-p` pede a senha de forma segura).
- **Por que executar:** produz um arquivo `loja_dump.sql` com a estrutura das tabelas (`clientes`, `produtos`, `pedidos`, `itens_pedido`, `carrinho`, `itens_carrinho`) e todos os dados atuais do MySQL local.
- **Validação:**
  ```bash
  ls -lh loja_dump.sql
  grep -c "CREATE TABLE" loja_dump.sql   # esperado: 6 (uma por tabela)
  head -n 20 loja_dump.sql               # confere o cabeçalho do dump
  ```
- **Resultado esperado:** arquivo `loja_dump.sql` criado, com 6 `CREATE TABLE` e os `INSERT` dos dados. **Não** deve conter `CREATE DATABASE loja` (por causa do `--no-create-db`).
- **Evidência:** print do `ls -lh loja_dump.sql` e do `grep -c "CREATE TABLE"` retornando `6`.

> **Nota — tabela de bloqueio (LOCK TABLES):** o RDS não concede a permissão de `SUPER`, e alguns dumps trazem instruções incompatíveis. O `--single-transaction` já evita `LOCK TABLES`. Se, no restore, aparecer erro relacionado a `DEFINER` de views/procedures, gere o dump adicionando `--set-gtid-purged=OFF` (quando aplicável) ou remova a cláusula `DEFINER` do arquivo antes de importar. Para este laboratório (apenas tabelas e dados), o comando acima é suficiente.

### Passo A.2 — Restaurar o dump no RDS

- **Comando (na EC2):**
  ```bash
  mysql -h <ENDPOINT-DO-RDS> -u admin -p loja < loja_dump.sql
  ```
  - **O que faz:** conecta no **RDS** como usuário mestre `admin` (o `-p` pede a senha), seleciona o banco `loja` (já existente) e executa todo o conteúdo do `loja_dump.sql`, criando as tabelas e inserindo os dados.
  - **Por que executar:** leva a estrutura e os dados do MySQL local para o banco `loja` do RDS — este é o coração da migração (Requisito 3.3).
- **Resultado esperado:** o comando termina **sem erros** e retorna ao prompt. (Se pedir a senha e for aceita, e nenhuma mensagem de erro aparecer, a importação foi concluída.)
- **Evidência:** print do terminal mostrando o comando executado sem erros.

Prossiga para **Criar o usuário de aplicação no RDS** e depois **Validação pós-migração** (seções comuns abaixo).

---

## Abordagem B — Reconstruir do zero com os scripts versionados

Use esta abordagem para popular o RDS **sem depender** do estado do banco local, reaproveitando os scripts que já estão no repositório.

> **Importante:** os scripts `sql/01_schema.sql` e `sql/02_seed.sql` começam com `USE loja;` e **não** executam `CREATE DATABASE`. Como o RDS já tem o banco `loja`, eles funcionam direto no RDS. O `sql/00_create_database.sql` **não** deve ser usado no RDS, pois ele cria `app_loja@'localhost'` (host que não serve no RDS) e tentaria criar o database — no RDS use o `sql/03_create_app_user_rds.sql` (ver seção seguinte).

### Passo B.1 — Aplicar o schema no RDS

- **Comando (na EC2, no diretório `sql/`):**
  ```bash
  cd /opt/aws-database-lab/sql   # ajuste para onde os scripts estão na EC2

  mysql -h <ENDPOINT-DO-RDS> -u admin -p loja < 01_schema.sql
  ```
  - **O que faz:** cria as 6 tabelas do modelo (`clientes`, `produtos`, `pedidos`, `itens_pedido`, `carrinho`, `itens_carrinho`) no banco `loja` do RDS.
- **Resultado esperado:** comando concluído sem erros.

### Passo B.2 — Inserir os dados de exemplo no RDS

- **Comando:**
  ```bash
  mysql -h <ENDPOINT-DO-RDS> -u admin -p loja < 02_seed.sql
  ```
  - **O que faz:** insere 5 produtos (Notebook, Mouse, Teclado, Monitor, Headset), 3 clientes e 2 pedidos com seus itens.
- **Resultado esperado:** comando concluído sem erros; as contagens devem bater na validação (5/3/2).
- **Evidência:** print dos dois comandos executados sem erros.

Prossiga para **Criar o usuário de aplicação no RDS** e depois **Validação pós-migração**.

---

## Criar o usuário de aplicação no RDS (`app_loja@'%'`) — comum às duas abordagens

> **Por que este passo é obrigatório (Requisito 11):** o RDS foi criado com o usuário **mestre `admin`**, que é administrativo e **não** deve ser usado pela aplicação. Além disso, o usuário `app_loja@'localhost'` do MySQL local **não serve** no RDS: a aplicação conecta pela **rede** (a EC2 é um host diferente do banco), e o host `localhost` só casa com conexões da própria máquina do servidor. Por isso criamos `app_loja@'%'`, com privilégios **apenas** no banco `loja`. O isolamento de rede continua garantido pelo `sg-db-lab` (só a EC2 alcança a porta 3306).

- **Antes de executar:** edite `sql/03_create_app_user_rds.sql` e troque o placeholder `ALTERE_ESTA_SENHA` por uma **senha forte real**. Essa mesma senha irá em `DB_PASSWORD` do `.env` na Tarefa 16 (nunca versionada).
- **Comando (na EC2, no diretório `sql/`):**
  ```bash
  mysql -h <ENDPOINT-DO-RDS> -u admin -p < 03_create_app_user_rds.sql
  ```
  - **O que faz:** conectado como `admin`, cria `app_loja'@'%'` e concede a ele **apenas** `SELECT, INSERT, UPDATE, DELETE` em `loja.*`.
- **Validação:**
  ```bash
  # ainda como admin, conferir o usuário e os privilégios:
  mysql -h <ENDPOINT-DO-RDS> -u admin -p -e \
    "SELECT user, host FROM mysql.user WHERE user='app_loja'; SHOW GRANTS FOR 'app_loja'@'%';"

  # testar login do usuário de aplicação (nova sessão):
  mysql -h <ENDPOINT-DO-RDS> -u app_loja -p loja -e "SELECT 1 AS conexao_ok;"
  ```
- **Resultado esperado:** `app_loja` aparece com `host = %`; o `SHOW GRANTS` mostra privilégios **restritos a `loja.*`**; o login como `app_loja` retorna `conexao_ok = 1`.
- **Evidência:** print do `SHOW GRANTS FOR 'app_loja'@'%'` e do `SELECT 1` bem-sucedido com o usuário `app_loja`.

---

## Validação pós-migração (Requisito 14.4 — "Disponível" não basta)

> Objetivo: **comprovar** que os dados chegaram ao RDS conferindo tabelas e contagens. O Requisito 14.4 exige comprovar o funcionamento, não apenas ver a instância "Disponível".

- **Comando (na EC2):**
  ```bash
  mysql -h <ENDPOINT-DO-RDS> -u admin -p loja
  ```
  Já conectado, execute:
  ```sql
  SHOW TABLES;
  -- Esperado (6): carrinho, clientes, itens_carrinho, itens_pedido, pedidos, produtos

  SELECT COUNT(*) AS total_produtos FROM produtos;   -- esperado: 5
  SELECT COUNT(*) AS total_clientes FROM clientes;   -- esperado: 3
  SELECT COUNT(*) AS total_pedidos  FROM pedidos;    -- esperado: 2

  -- Amostra dos produtos migrados (nome + referência de imagem):
  SELECT id, nome, preco, estoque, imagem FROM produtos ORDER BY id;

  -- Confere o total do pedido 1 a partir dos itens (deve bater com 4689.80):
  SELECT p.id, p.total,
         SUM(ip.quantidade * ip.preco_unitario) AS total_calculado
  FROM pedidos p
  JOIN itens_pedido ip ON ip.pedido_id = p.id
  GROUP BY p.id, p.total;

  EXIT;
  ```
- **O que faz:** lista as tabelas no RDS e confere as contagens dos dados migrados.
- **Resultado esperado:** `SHOW TABLES;` lista as **6 tabelas**; as contagens retornam **5 produtos, 3 clientes e 2 pedidos**; o total calculado do pedido 1 bate com `4689.80`. Isso comprova que a migração levou estrutura **e** dados para o RDS.
- **Evidência:** print do `SHOW TABLES;` (6 tabelas) e das três contagens (5/3/2), guardado em `evidencias/` (ex.: `NN-rds-migracao-contagens.png`).

---

## Segurança — resumo (Requisito 11)

- A aplicação **não** usa o usuário mestre `admin`; usa `app_loja@'%'` com privilégios **apenas** em `loja.*`.
- Senhas **não** ficam no código nem no repositório: senha do `admin` definida no Console; senha do `app_loja` via placeholder no SQL e, na aplicação, via `DB_PASSWORD` no `.env` (fora do Git — ver `.gitignore`).
- O acesso ao RDS na porta `3306` é liberado **somente** para a EC2, via `sg-db-lab` com origem = `sg-ec2-lab` (nunca `0.0.0.0/0`).

## Limpeza (opcional)

Após validar a migração, o arquivo de dump pode ser removido da EC2 para não deixar dados fora do banco:
```bash
rm -f /opt/aws-database-lab/loja_dump.sql
```

## Próximo passo — Tarefa 16

Apontar a aplicação para o RDS: no `.env`, alterar `DB_WRITER_ENDPOINT` para o **endpoint do RDS** (mantendo `DB_NAME=loja`), usar `DB_USER=app_loja` e a senha do `app_loja` em `DB_PASSWORD`, reiniciar o serviço e validar `INSERT/SELECT/UPDATE/DELETE`, atualizando o painel `/database-lab` para **"Banco = RDS MySQL (Single-AZ)"** e documentando **"compute separado de database"**.
