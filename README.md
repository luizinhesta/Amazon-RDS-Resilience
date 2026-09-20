# Da EC2 Monolítica ao RDS Resiliente: Eliminando o Ponto Único de Falha

> Documento de informação do **AWS RDS Resilience Lab**: a jornada da loja **AWS Database Lab Store**, da Fase 0 (monolito em uma EC2) à Fase 4 (imagens no S3), com o raciocínio por trás de cada decisão. Os números da execução real (tempo de failover, `ReplicaLag`) ficam em `TESTES.md` e em `evidencias/`.
>
> **Demais documentos:** `ARQUITETURA.md` (ANTES/DEPOIS de cada fase), `IMPLANTACAO.md` (passo a passo no Console + comandos na EC2), `TESTES.md` (matriz de testes com resultados) e `EXCLUSAO.md` (limpeza/custo ao pausar ou encerrar).

![Descrição da imagem](<imagens/imagem%20(1).png>)

## O problema

Toda arquitetura resiliente começa com uma que **não é** resiliente. A loja nasceu rodando **inteira dentro de uma única EC2**: aplicação Flask, servidor MySQL, banco `loja`, arquivos estáticos (HTML/CSS/JS) e imagens dos produtos, com um domínio no Route 53 apontando para o IP público da instância.

```text
Fase 0 (monolito)
Usuário → Route 53 → EC2 [ Flask + MySQL + banco loja + HTML/CSS/JS + imagens ]
```

Isso é um **SPOF — Single Point of Failure**: compute (a aplicação) e estado (banco e arquivos) acoplados no mesmo recurso, com o mesmo ciclo de vida. Se a EC2 cair, **tudo cai junto** — e o pior nem é a indisponibilidade, mas o fato de o **estado durável morar junto com o compute efêmero**: não dá para reiniciar, atualizar ou trocar a instância sem arriscar os dados, nem escalar leitura, disponibilidade e arquivos de forma independente.

A aplicação, porém, já nasceu pronta para a evolução: credenciais só em variáveis de ambiente (`.env`, fora do Git); `db.py` com **writer** e **reader** separados (na Fase 0 ambos em `localhost`); `storage.py` com modos `local` e `s3`; e a página `/database-lab` mostrando o banco em uso e a conectividade. A ideia central: **o código não muda entre as fases — muda a configuração**.

## A decisão: desacoplar em etapas

O primeiro problema a atacar não é "adicionar redundância a tudo" — é **desacoplar**, um problema por fase, cada passo justificado por uma dor concreta da fase anterior:

| Fase | Tema | Problema que resolve |
|---|---|---|
| 0 | Monolito em EC2 | Linha de base (SPOF), propositalmente frágil |
| 1 | RDS Single-AZ | Separar compute de database |
| 2 | RDS Multi-AZ | Alta disponibilidade (failover automático) |
| 3 | RDS Read Replica | Escalabilidade de leitura |
| 4 | Imagens no S3 | Arquivos independentes da EC2 |

![Descrição da imagem](<imagens/imagem%20(3).png>)

## A implementação (o raciocínio)

Toda a infraestrutura foi criada **manualmente no Console AWS, em pt-BR** — para conhecer cada campo, não automatizar. O passo a passo está em `IMPLANTACAO.md`.

- **Fase 1 — RDS Single-AZ.** Security Group do banco (`sg-db-lab`) libera a porta 3306 **só** com origem no SG da EC2 (`sg-ec2-lab`), nunca `0.0.0.0/0`; RDS com "Acesso público = Não". Migrei o dump do MySQL local e criei um usuário de menor privilégio (`app_loja`). Para a app usar o RDS, mudei **uma linha** no `.env` (`DB_WRITER_ENDPOINT`). Sem tocar no código — o `config.py` **deduz o tipo de banco pelo endpoint** e passou a exibir "RDS MySQL — Single-AZ".
- **Fase 2 — Multi-AZ.** Uma modificação no Console: a AWS provisiona um **standby síncrono em outra AZ**. O endpoint não muda. Zero alteração de `.env` ou código.
- **Fase 3 — Read Replica.** Criei uma réplica de leitura **assíncrona**. Bastou preencher `DB_READER_ENDPOINT` no `.env`: as escritas seguem no writer, as leituras vão ao reader, e o `db.py` **loga qual endpoint usou** (`[WRITER]`/`[READER]`) — a prova do roteamento.
- **Fase 4 — S3.** Bucket criado, imagens enviadas, `STORAGE_MODE=s3`. O banco guarda só a **referência** (chave/URL); o binário nunca entra no MySQL.

## A prova: falha simulada + observabilidade

Um recurso não vale porque o Console diz "Disponível" — vale quando há **evidência**. Antes de provocar falhas, montei a observabilidade: dashboard CloudWatch `db-lab-01-rds` (CPU, conexões, storage, latências, IOPS, `ReplicaLag`), um alarme didático, o Log Group `/aws/events/db-lab-01-rds` e a regra EventBridge com o fluxo **`RDS → EventBridge → CloudWatch Logs`**.

Na Fase 2, forcei um failover ("Reiniciar com failover") enquanto um loop de `SELECT 1` media a indisponibilidade. O resultado foi o esperado: **breve indisponibilidade** (`OK → FALHA → OK`), a AWS reapontou o DNS do endpoint para o novo primário, e a app **reconectou sozinha ao mesmo nome**. O failover foi comprovado por **três fontes que convergem**: o evento `failover` no Log Group, o degrau nas métricas e a janela do loop.

Um detalhe revelador: na Fase 2 o widget `ReplicaLag` ficou **"Sem dados"** — não era bug, era a **prova** de que o standby Multi-AZ não é legível. Na Fase 3, com a Read Replica, ele **passou a exibir valores** — a transição visual comprova que agora existe réplica ativa.

## Arquitetura final e aprendizado

```text
Usuário → Route 53 → EC2 (Flask)
                       ├── RDS MySQL (Multi-AZ) → Read Replica (leitura)
                       └── Amazon S3 (imagens)
Observabilidade: CloudWatch + EventBridge + CloudWatch Logs
```
![Descrição da imagem](<imagens/imagem%20(2).png>)

O SPOF do banco foi eliminado (Multi-AZ), a leitura ficou escalável (Read Replica) e os arquivos desacoplados (S3) — **sem reescrever a aplicação**, só evoluindo configuração e infraestrutura.

O aprendizado central é a diferença **prática** entre disponibilidade e escalabilidade de leitura:

| Aspecto | Multi-AZ (Fase 2) | Read Replica (Fase 3) |
|---|---|---|
| Resolve | Alta disponibilidade / failover | Escalabilidade de leitura |
| Replicação | Síncrona | Assíncrona (→ `ReplicaLag`) |
| Secundário atende leitura? | Não (standby em espera) | Sim (reader recebe `SELECT`) |
| `ReplicaLag` no dashboard | "Sem dados" | Exibe valores |

São **complementares** (podem coexistir), mas resolvem coisas diferentes. Outros princípios exercitados: desacoplar compute de estado (Confiabilidade do Well-Architected), segurança por referência de Security Group (sem `0.0.0.0/0`) e credenciais fora do código, S3 para conteúdo estático, e observabilidade como forma de **comprovar** comportamento em falhas. Por custo, Multi-AZ e Read Replica podem ser revertidos entre fases quando não estão em teste — escolha consciente de laboratório.

## Serviços utilizados

Amazon EC2, Amazon RDS (MySQL), Read Replica, Amazon S3, Amazon Route 53, Amazon CloudWatch, Amazon EventBridge, CloudWatch Logs.

## Próximo passo

O **Projeto 02** migra a mesma aplicação do RDS MySQL para o **Aurora MySQL**, reaproveitando quase tudo e explorando failover mais rápido e o **Aurora Clone (copy-on-write)**.
