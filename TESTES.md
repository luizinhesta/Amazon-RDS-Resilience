# Testes — Da EC2 Monolítica ao RDS Resiliente: Eliminando o Ponto Único de Falha

Matriz de testes da **AWS Database Lab Store**, da Fase 0 (monolito) à Fase 4 (S3). Padrão de cada linha: **Teste / Objetivo / Procedimento / Resultado esperado / Resultado observado / Evidência** (Req. 13.5), com testes positivos e de falha.

**Convenções**
- Testes de interface executados manualmente (navegador/Console). "Resultado observado" fica `( a preencher )` até a execução.
- Evidências em `evidencias/` no padrão `NN-descricao.png|.log`.
- Passo a passo detalhado dos procedimentos: ver `IMPLANTACAO.md`. Contexto arquitetural: `README.md`.
- Seed carregado: 5 produtos, 3 clientes, 2 pedidos (Pedido #1 = R$ 4689,80; Pedido #2 = R$ 1399,70).

---

## Fase 0 — CRUD e imagens (monolito, MySQL local)

| Teste | Objetivo | Procedimento | Resultado esperado | Resultado observado | Evidência |
|---|---|---|---|---|---|
| T8.1 Listar produtos | Leitura (Req. 1.1/1.2) | Acessar `/produtos` | Lista os 5 produtos do seed | ( a preencher ) | `08-listar-produtos.png` |
| T8.2 Cadastrar produto | INSERT (Req. 1.2) | `/produtos` → cadastrar `Webcam` e salvar | Sucesso; produto aparece na lista | ( a preencher ) | `08-cadastrar-produto.png` |
| T8.3 Editar produto | UPDATE (Req. 1.2) | `/produtos` → editar `Mouse` (preço/estoque) | Sucesso; alteração refletida | ( a preencher ) | `08-editar-produto.png` |
| T8.4 Persistência | Durabilidade (Req. 2.7) | Recarregar `/produtos` após T8.3 | Alteração persiste | ( a preencher ) | `08-persistencia-edicao.png` |
| T8.5 Produto sem nome (falha) | Campo obrigatório | POST `/produtos/salvar` sem `nome` | Rejeita: "O nome do produto é obrigatório."; nada criado | ( a preencher ) | `08-falha-produto-sem-nome.png` |
| T9.1 Listar clientes | Leitura (Req. 1.3) | Acessar `/clientes` | Lista os 3 clientes do seed | ( a preencher ) | `09-listar-clientes.png` |
| T9.2 Cadastrar cliente | INSERT (Req. 1.3) | `/clientes` → cadastrar `Daniel Rocha` | Sucesso; cliente na lista | ( a preencher ) | `09-cadastrar-cliente.png` |
| T9.3 Persistência | Durabilidade (Req. 2.7) | Recarregar `/clientes` após T9.2 | Cliente persiste | ( a preencher ) | `09-persistencia-cliente.png` |
| T9.4 Cliente sem nome/e-mail (falha) | Campos obrigatórios | POST sem `nome`/`email` | Rejeita: "Nome e e-mail são obrigatórios." | ( a preencher ) | `09-falha-cliente-sem-campos.png` |
| T9.5 E-mail duplicado (falha) | Restrição UNIQUE (Req. 2.2) | Cadastrar e-mail já existente | Rejeita: "Não foi possível cadastrar o cliente (e-mail já existe?)." | ( a preencher ) | `09-falha-email-duplicado.png` |
| T10.1 Listar pedidos | Leitura (Req. 1.4) | Acessar `/pedidos` | Lista os 2 pedidos do seed (id desc) | ( a preencher ) | `10-listar-pedidos.png` |
| T10.2 Criar pedido | INSERT pedidos+itens (Req. 1.4) | `/pedidos` → Carla + 2× Headset | Sucesso; redireciona ao detalhe (total R$ 639,80) | ( a preencher ) | `10-criar-pedido.png` |
| T10.3 Detalhe do pedido | Leitura de itens (Req. 1.4) | `/pedidos?detalhe=2` | Itens do #2 com subtotal = preço × qtd | ( a preencher ) | `10-consultar-pedido.png` |
| T10.4 Cálculo do total | Total = soma dos subtotais (Req. 1.4) | Conferir totais dos pedidos | Cabeçalho bate com a soma dos itens | ( a preencher ) | `10-calculo-total.png` |
| T10.5 Persistência | Durabilidade (Req. 2.7) | Recarregar `/pedidos` após T10.2 | Pedido persiste | ( a preencher ) | `10-persistencia-pedido.png` |
| T10.6 Pedido sem cliente/produto (falha) | Campos obrigatórios | POST sem `cliente_id`/`produto_id` | Rejeita: "Selecione cliente e produto para criar o pedido." | ( a preencher ) | `10-falha-pedido-sem-itens.png` |
| T11.1 Imagens na home | Imagens da EC2 (Req. 1.6) | Acessar `/` | 5 imagens SVG de `/static/images/`; nenhuma quebrada | ( a preencher ) | `11-imagens-produtos.png` |
| T11.2 Miniaturas | Imagens em `/produtos` (Req. 1.6) | Acessar `/produtos` | Miniaturas servidas da EC2 | ( a preencher ) | `11-miniaturas-produtos.png` |
| T11.3 HTTP direto ao estático | Estático da EC2 (Req. 1.6) | `curl -I .../static/images/notebook.svg` | HTTP 200 | ( a preencher ) | `11-http-200-static.png` |
| T11.4 Fallback sem-imagem | Imagem NULL (Req. 1.6) | Produto sem `imagem` | Usa `sem-imagem.svg` (sem quebra) | ( a preencher ) | `11-fallback-sem-imagem.png` |
| T11.5 Banco guarda só referência | Modelo de dados (Req. 6.4) | `SELECT imagem FROM produtos` | Só o nome do arquivo, nunca binário | ( a preencher ) | `11-banco-referencia-imagem.log` |

**CHECKPOINT 01 (Tarefa 12 — bloqueante, Req. 2.8):** só liberar a Fase 1 (RDS) após comprovar C1–C11 abaixo. Os testes de CRUD/imagem reusam T8–T11.

| Item | Objetivo | Verificação | Evidência |
|---|---|---|---|
| C1 Abrir a loja | Acesso (2.6) | `/` carrega com produtos | `12-01-abrir-loja.png` |
| C2–C7 CRUD + imagens | Fluxo completo (2.6/2.7) | Reusar T8.1/T8.2, T9.2, T10.2/T10.3, T11.1 | `12-02..07-*.png` |
| C8 Persistência após restart do Flask | Durabilidade (2.7) | Reiniciar só o Flask; dados permanecem | `12-08-persistencia-restart-app.png` |
| C9 MySQL ativo | Banco na EC2 (2.7) | `systemctl status mysqld` = running | `12-09-mysql-status.log` |
| C10 Conexão local | `SELECT 1` (2.7) | `/database-lab`: WRITER `localhost:3306` OK | `12-10-conexao-local.png` |
| C11 Painel Fase 0 | Painel (1.7) | `/database-lab`: "MySQL local", "Fase 0 — Monolito em EC2" | `12-11-database-lab.png` |

---

## Fase 1 — RDS Single-AZ (Tarefa 16)

> Reaponta o `.env` (`DB_WRITER_ENDPOINT` = endpoint do RDS) sem alterar código. O `config.py` deduz "RDS MySQL — Single-AZ" pelo hostname. Detalhe: `IMPLANTACAO.md`, Fase 1.

| Teste | Objetivo | Procedimento | Resultado esperado | Resultado observado | Evidência |
|---|---|---|---|---|---|
| T1.1 Conectividade ao RDS | `SELECT 1` no RDS (Req. 3.4) | `mysql -h ENDPOINT_RDS -u app_loja -p loja -e "SELECT 1;"` | Login OK; `conexao_ok = 1` | ( a preencher ) | `16-01-conexao-rds.png` |
| T1.2 Serviço no endpoint do RDS | App recarrega `.env` (Req. 3.4) | `journalctl -u aws-database-lab` | Log `[WRITER] -> endpoint=rds-mysql-lab...:3306` | ( a preencher ) | `16-02-log-endpoint-rds.log` |
| T1.3 Painel Fase 1 | Painel reflete RDS (Req. 1.7/3.6) | Acessar `/database-lab` | "Fase 1 — RDS Single-AZ"; "RDS MySQL — Single-AZ"; WRITER OK | ( a preencher ) | `16-03-database-lab-rds.png` |
| T1.4–T1.7 CRUD no RDS | INSERT/SELECT/UPDATE/DELETE (Req. 3.5) | CRUD pela loja + conferência via `mysql -h ENDPOINT_RDS` | Efeito refletido no RDS em todas as operações | ( a preencher ) | `16-04..07-*` |
| T1.8 Dados no RDS | Compute separado de database (Req. 3.6) | `SELECT COUNT(*)` no RDS vs. loja | Contagem do RDS bate com a loja | ( a preencher ) | `16-08-dados-no-rds.log` |

---

## Fase 2 — RDS Multi-AZ (teste de falha)

> Multi-AZ = alta disponibilidade (standby síncrono, **não** legível). Failover mantém o **mesmo endpoint**. Detalhe: `IMPLANTACAO.md`, Fase 2. Custo: Multi-AZ dobra o custo de instância; pode ser revertido a Single-AZ após a T2.2.

| Teste | Objetivo | Procedimento | Resultado esperado | Resultado observado | Evidência |
|---|---|---|---|---|---|
| T2.0 Conversão Multi-AZ | Pré-condição do failover (Req. 4.2) | Modificar `rds-mysql-lab` → Multi-AZ; conferir aba Configuração | Multi-AZ = Sim, duas AZs; loja segue no mesmo endpoint | CONFORME. Multi-AZ = Sim em duas AZs (us-east-1); loja seguiu no mesmo endpoint, `/database-lab` WRITER OK sem reconfigurar. | `18-multi-az-config.png` |
| T2.1 Failover | HA + medir recuperação (Req. 4.3/4.4/4.5) | Loop `SELECT 1` a cada 1s; `Ações → Reiniciar com failover`; medir janela `OK → FALHA → OK` | Standby promovido; endpoint não muda; app reconecta sozinha | CONFORME. `OK → FALHA → OK` com recuperação ≈ 2min17s (20:55:43 → 20:58:00, UTC-03). Endpoint inalterado; app reconectou (WRITER OK). | `19-loop-select1.log`, `19-failover-evento-console.png`, `19-database-lab-pos-failover.png` |
| T2.2 Evidências do failover | Evento + métricas (Req. 4.6/7) | Logs Insights (`filter EventCategories.0 = "failover"`); aba Eventos; degrau em `DatabaseConnections`/latências | 3 fontes convergem no mesmo intervalo; `ReplicaLag` = "Sem dados" | CONFORME. Loop + aba Eventos + evento `failover` no Log Group (RDS-EVENT-0049, 2026-09-17T20:56:33Z) convergem. `ReplicaLag` sem dados (esperado). | `20-evento-failover.png`, `20-rds-aba-eventos.png`, `20-dashboard-degrau.png` |

---

## Fase 3 — RDS Read Replica

> Read Replica = escalabilidade de leitura (assíncrona, com `ReplicaLag`). Preencher `DB_READER_ENDPOINT` no `.env` faz o roteamento leitura/escrita. Detalhe: `IMPLANTACAO.md`, Fase 3. Custo: réplica é instância extra; pode ser excluída após a T3.2.

| Teste | Objetivo | Procedimento | Resultado esperado | Resultado observado | Evidência |
|---|---|---|---|---|---|
| T3.1 Roteamento leitura/escrita | Writer para escrita, reader para leitura (Req. 5.3–5.6) | Definir `DB_READER_ENDPOINT`; reiniciar; observar logs `[WRITER]`/`[READER]` | Painel WRITER OK + READER OK (endpoints distintos); logs comprovam roteamento | CONFORME. Painel WRITER OK + READER OK ("Writer + Read Replica"). Logs: leitura `[READER] -> ...-replica...`; escrita `[WRITER] -> ...`. | `22-roteamento.log`, `22-database-lab-writer-reader.png` |
| T3.2 Replicação e `ReplicaLag` | Consistência eventual (Req. 5.7/5.8/7) | INSERT no writer; SELECT no reader; conferir widget `ReplicaLag` | Dado aparece no reader após pequeno atraso; `ReplicaLag` passa a exibir valores | CONFORME. Contagens iguais writer/reader (6); `ReplicaLag`, antes "Sem dados", passou a exibir valores ≈ 0 — réplica ativa. | `23-replicacao.png`, `23-replicalag.png` |

---

## Fase 4 — Imagens no S3

> Imagens servidas do S3; banco guarda só a referência. Detalhe: `IMPLANTACAO.md`, Fase 4 (+ `scripts/upload_imagens_s3.md`).

| Teste | Objetivo | Procedimento | Resultado esperado | Resultado observado | Evidência |
|---|---|---|---|---|---|
| T4.1 Imagens do S3 | Independência da EC2 (Req. 6.2–6.5) | `aws s3 sync` dos SVGs; `curl` da URL; `STORAGE_MODE=s3`; reiniciar; conferir loja e banco | `curl` = 200; `src` aponta para URL do S3; painel lista S3; `produtos.imagem` só com o nome do arquivo | ( a preencher ) | `24-imagens-s3.png`, `24-bucket-s3.png`, `24-bucket-policy.png`, `24-iam-role-ec2.png` |

---

## Validação final (Tarefa 25)

Arquitetura final: **EC2 (app) + RDS MySQL (banco) + S3 (imagens)**, desacoplados. Multi-AZ (Req. 4) e Read Replica (Req. 5) foram comprovados nas Fases 2/3 e podem estar revertidos/excluídos por custo (Req. 12) sem invalidar a comprovação. O painel `/database-lab` deduz a arquitetura do `.env` (sem rótulo fixo).

| Item | Verificação | Evidência |
|---|---|---|
| F1 Loja funcional | CRUD ponta a ponta sobre EC2 + RDS + S3 | `25-01-loja-funcional.png` |
| F2 Banco no RDS | `SELECT COUNT(*)` no RDS bate com a loja; log aponta endpoint do RDS | `25-02-banco-no-rds.log` |
| F3 HA Multi-AZ | Comprovado na Fase 2 (T2.0–T2.2); registrar estado atual | `18-multi-az-config.png`, `19-loop-select1.log`, `20-evento-failover.png` |
| F4 Escala de leitura | Comprovado na Fase 3 (T3.1–T3.2); registrar estado atual | `22-roteamento.log`, `23-replicalag.png` |
| F5 Imagens no S3 | `src` = URL do S3; `curl` 200; banco só referência | `25-05-imagens-s3-final.png` |
| F6 Painel final | RDS (+ reader opcional) + S3, deduzido do `.env` | `25-06-database-lab-final.png` |

**Configuração recomendada ao encerrar (Req. 12):** RDS Single-AZ + imagens no S3, com Multi-AZ revertido e Read Replica excluída (`DB_READER_ENDPOINT` vazio). Nessa config o painel exibe "RDS MySQL — Single-AZ" + "Amazon S3". Lista completa de limpeza: `EXCLUSAO.md`.
