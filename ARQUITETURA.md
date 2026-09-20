# Arquitetura — Da EC2 Monolítica ao RDS Resiliente: Eliminando o Ponto Único de Falha

Este documento mostra sempre **ANTES vs. DEPOIS** a cada fase (Requisito 13.3). Cada evolução só é adotada depois que um **problema concreto** da fase anterior a justifica.

---

## Fase 0 — Monolito em EC2 (linha de base)

A Fase 0 é a linha de base **propositalmente frágil**. Tudo roda dentro de uma única instância Amazon EC2: a aplicação Flask, o servidor MySQL, o banco `loja`, os arquivos estáticos (HTML/CSS/JS) e as imagens dos produtos.

### Diagrama (estado atual)

```text
                        Usuário (navegador)
                              │
                              ▼
              Route 53  (SEU_DOMINIO)
                              │
                              ▼
   ┌─────────────────────────────────────────────────────┐
   │                 Amazon EC2 (única)                    │
   │                                                       │
   │   ┌───────────────┐      ┌────────────────────────┐  │
   │   │ Aplicação      │     │ MySQL Server           │  │
   │   │ Flask (app.py) │────▶│  └── Banco "loja"       │  │
   │   └───────────────┘      │      (clientes,         │  │
   │           │              │       produtos,         │  │
   │           │              │       pedidos, ...)     │  │
   │           ▼              └────────────────────────┘  │
   │   ┌───────────────┐      ┌────────────────────────┐  │
   │   │ HTML/CSS/JS    │     │ Imagens dos produtos    │  │
   │   │ (static/)      │     │ (static/images/)        │  │
   │   └───────────────┘      └────────────────────────┘  │
   │                                                       │
   └─────────────────────────────────────────────────────┘
             ▲
             └── TUDO em um só lugar = 1 ponto de falha
```

### O problema: SPOF total (Single Point of Failure)

Um **SPOF (Single Point of Failure)** é um ponto único cuja falha derruba o sistema inteiro. Nesta arquitetura, a própria EC2 é esse ponto: **compute (aplicação) e estado (banco + arquivos) estão acoplados no mesmo recurso**.

Se a instância EC2 ficar indisponível — por falha de hardware do host, problema na Zona de Disponibilidade (AZ), reboot, esgotamento de disco/memória, erro de configuração ou parada acidental — **todos os componentes caem ao mesmo tempo e simultaneamente** (Requisito 2.9):

| Componente | O que acontece se a EC2 cair | Consequência |
|---|---|---|
| Aplicação Flask | Para de responder | Site fora do ar |
| MySQL + banco `loja` | Fica inacessível | Sem leitura/escrita de dados |
| Imagens dos produtos | Deixam de ser servidas | Loja quebrada visualmente |
| Arquivos estáticos (HTML/CSS/JS) | Deixam de ser servidos | Interface indisponível |

Não há isolamento de falhas: **não existe uma única parte que continue funcionando** quando a EC2 cai.

### Por que isso é ruim (análise)

- **Blast radius máximo:** uma falha em qualquer camada afeta todas as outras, porque compartilham o mesmo host, o mesmo sistema operacional e o mesmo ciclo de vida.
- **Sem tolerância a falhas:** não há redundância. A falha de um único recurso é igual à falha do sistema inteiro.
- **Estado acoplado ao compute:** o banco de dados (estado durável) vive no mesmo lugar que a aplicação (compute efêmero). Não é possível substituir/reiniciar/escalar a EC2 sem colocar os dados em risco.
- **Manutenção intrusiva:** qualquer patch, upgrade ou reinício do MySQL exige mexer na mesma máquina que serve os usuários — sem janela segura.
- **Impossível escalar por camada:** não dá para escalar leitura do banco, disponibilidade do banco ou entrega de arquivos de forma independente.
- **Backup/recuperação frágeis:** a durabilidade dos dados depende da sobrevivência de uma única instância.

### Princípios de arquitetura aplicados

Este cenário é o "antipadrão" clássico de arquitetura de soluções na nuvem:

- **Eliminar SPOFs** é um princípio central de arquitetura; a solução correta quase sempre envolve **desacoplar** e **adicionar redundância**.
- **Alta disponibilidade (High Availability)** e **tolerância a falhas (Fault Tolerance)** exigem distribuir componentes por **múltiplas Zonas de Disponibilidade (Multi-AZ)** e usar serviços gerenciados.
- O **AWS Well-Architected Framework** (pilar de **Confiabilidade / Reliability**) recomenda **separar compute de estado** e usar armazenamento/banco gerenciados em vez de manter tudo em uma instância.
- Trocar um banco autogerenciado dentro da EC2 por um serviço gerenciado (**Amazon RDS**) transfere para a AWS o trabalho pesado de patching, backup, recuperação e failover — reduzindo o risco operacional.

### Justificativa da próxima etapa

O primeiro problema a atacar é o **acoplamento entre compute e banco de dados**. A ação de maior impacto e menor complexidade é **separar o banco da EC2**, movendo o MySQL para o **Amazon RDS** (serviço gerenciado).

Isso não elimina todos os problemas de uma vez (imagens continuam na EC2, e o RDS começa em Single-AZ), mas **desacopla compute de database**: a aplicação passa a poder falhar, ser reiniciada ou substituída sem levar o banco junto. É o primeiro passo natural da cadeia de resiliência e prepara o terreno para Multi-AZ, Read Replica e S3 nas fases seguintes.

---

## Fase 1 — Separação do banco (RDS Single-AZ)

```text
ANTES (Fase 0)
┌───────────────────────────────┐
│ Amazon EC2                     │
│  app Flask + MySQL + banco     │
│  + imagens + arquivos          │   ← SPOF total
└───────────────────────────────┘

DEPOIS (Fase 1)
┌───────────────────────────────┐
│ Amazon EC2                     │
│  app Flask + imagens +         │
│  arquivos estáticos            │
└───────────────┬───────────────┘
                │ conexão 3306 (via Security Group)
                ▼
┌───────────────────────────────┐
│ Amazon RDS MySQL (Single-AZ)   │
│  banco "loja"                  │   ← serviço gerenciado
└───────────────────────────────┘
```

**Ganho:** compute separado de database (desacoplamento). O banco passa a ser gerenciado pela AWS (patching, backups automáticos, snapshots).

### Resultado alcançado (Tarefa 16 — compute separado de database)

Após criar o RDS (Tarefa 14), migrar os dados (Tarefa 15) e **reapontar a aplicação** para o endpoint do RDS (Tarefa 16 — `IMPLANTACAO.md`, Fase 1), a arquitetura foi validada na prática:

- A EC2 passou a hospedar **apenas o compute** — aplicação Flask e imagens locais (estas só migram na Fase 4). O **estado durável** (banco `loja`) vive agora no **Amazon RDS**, independente da instância.
- O reapontamento exigiu **somente configuração** (`DB_WRITER_ENDPOINT` = endpoint do RDS, `DB_USER=app_loja`, `DB_NAME=loja` mantido, `LAB_ARCH_VERSION=Fase 1 — RDS Single-AZ` no `.env`) — **nenhuma alteração de código** (Requisito 3.4). O painel `/database-lab` passou a exibir **"RDS MySQL — Single-AZ"** de forma **dinâmica**, deduzida do endpoint pelo `config.py` (`Config.tipo_banco()` / `Config.descrever_banco()`), mecanismo que também reconhece Aurora nas fases/projetos seguintes.
- O funcionamento foi comprovado por **CRUD real** (`INSERT/SELECT/UPDATE/DELETE`) em produtos, clientes e pedidos, com efeito confirmado diretamente no RDS (ver `TESTES.md`, Fase 1) — um recurso não é considerado válido só por aparecer "Disponível" (Requisito 14.4).

**Prova do desacoplamento:** com o banco fora da instância, a **EC2 pode ser reiniciada, substituída ou falhar sem levar os dados junto**; a AWS assume patching, backups automáticos e snapshots do RDS. Este é o primeiro passo da cadeia de resiliência e habilita as fases seguintes (Multi-AZ, Read Replica, S3).

**Limitações remanescentes (motivam as próximas fases):**
- RDS **Single-AZ** ainda tem risco de indisponibilidade de instância/AZ → resolvido na **Fase 2 (Multi-AZ)**.
- Toda a carga de leitura vai para a mesma instância → resolvido na **Fase 3 (Read Replica)**.
- **Imagens e arquivos ainda vivem na EC2** → resolvido na **Fase 4 (S3)**.

---

## Fase 2 — RDS Multi-AZ (alta disponibilidade)

```text
ANTES
EC2 → RDS (Single-AZ)

DEPOIS
EC2 → RDS Primary (AZ-a)  ⇄  RDS Standby (AZ-b)
              (failover automático)
```

**Ganho:** alta disponibilidade com failover automático entre AZs. **Observação importante:** Multi-AZ é **disponibilidade**, **não** escalabilidade de leitura — o standby não atende leituras no Multi-AZ tradicional.

### Resultado alcançado (Tarefas 18–20 — failover automático comprovado)

A Fase 2 percorreu o ciclo completo **IMPLEMENTAR → PROVOCAR FALHA → OBSERVAR → COMPROVAR**, encerrado na Tarefa 20 (análise das evidências). O passo a passo está no `IMPLANTACAO.md` (Fase 2) e os testes no `TESTES.md` (T2.0 a T2.2):

- **Multi-AZ habilitado (Tarefa 18):** a instância `rds-mysql-lab` passou a ter **primário + standby em AZs distintas**, com o **mesmo endpoint** de escrita — a conversão exigiu **apenas modificação no Console**, sem qualquer alteração de código ou no `.env` (o `DB_WRITER_ENDPOINT` não muda). O standby é mantido em sincronização **síncrona** e fica **em espera** (não atende leitura nem escrita).
- **Failover provocado e medido (Tarefa 19):** com "Reiniciar com failover" (Reboot with failover), a AWS **promoveu o standby da outra AZ a novo primário** e reapontou o **DNS do endpoint** (mesmo nome, IP possivelmente diferente). Houve **breve indisponibilidade** (dezenas de segundos a poucos minutos), medida por um loop de `SELECT 1`/`curl` a cada 1s; em seguida a aplicação **reconectou sozinha ao mesmo endpoint**, sem reconfiguração. O **tempo de recuperação** ficou registrado na T2.1 do `TESTES.md`.
- **Evidências analisadas (Tarefa 20):** o failover foi comprovado por **três fontes independentes que convergem para o mesmo intervalo**: **(1)** o evento de categoria **`failover`** no Log Group `/aws/events/db-lab-01-rds` (fluxo `RDS → EventBridge → CloudWatch Logs`, localizado via CloudWatch Logs Insights), com **conferência cruzada** na aba **Eventos** do RDS; **(2)** o **degrau** nas métricas do dashboard `db-lab-01-rds` (queda e retomada de `DatabaseConnections`, oscilação de `ReadLatency`/`WriteLatency`); **(3)** a janela `OK → FALHA → OK` do loop de medição da T2.1. Um recurso não é considerado válido só por aparecer "Disponível" — o funcionamento foi comprovado por teste (Requisito 14.4).

**Conclusão comprovada — Multi-AZ = alta disponibilidade (Requisitos 4.5 e 4.6):** o failover foi **automático** (a AWS promoveu o standby sem intervenção manual), o **endpoint não mudou** e o serviço voltou em poucos segundos/minutos — exatamente o comportamento de **alta disponibilidade** de instância/AZ.

### Distinção didática — Multi-AZ (disponibilidade) vs. Read Replica (escala de leitura)

Esta é uma distinção fundamental que a Fase 2 comprova na prática:

| Recurso | Problema que resolve | Como replica | O papel secundário atende leitura? | Métrica de interesse |
|---|---|---|---|---|
| **Multi-AZ (Fase 2)** | **Alta disponibilidade** / failover automático de instância/AZ | **Síncrona** | **Não** — o standby fica em espera, só assume no failover | `ReplicaLag` = **"Sem dados"** (não há réplica legível) |
| **Read Replica (Fase 3)** | **Escalabilidade de leitura** | **Assíncrona** | **Sim** — endpoint legível recebe `SELECT` | `ReplicaLag` passa a ter dados |

- A métrica `ReplicaLag` aparecendo **"Sem dados"** no dashboard durante a Fase 2 é a **prova concreta** de que **não há réplica de leitura** — o Multi-AZ tradicional **não aumenta a capacidade de leitura**.
- **Regra prática:** "preciso de **alta disponibilidade / failover automático**" → **Multi-AZ**; "preciso **escalar leituras**" → **Read Replica**. São recursos **complementares** (podem coexistir), mas resolvem **problemas diferentes**. A **escalabilidade de leitura** é justamente o objeto da **Fase 3 (Read Replica, Tarefas 21–23)**, onde o widget `ReplicaLag` passará a exibir dados.

> **Custo (Requisito 12):** como o Multi-AZ **dobra o custo de instância** (primário + standby) e já cumpriu seu papel didático ao final da Tarefa 20, e como a **Fase 3 não exige Multi-AZ**, pode-se **reverter para Single-AZ** para economizar antes de prosseguir (guia no `EXCLUSAO.md`).

---

## Fase 3 — RDS Read Replica (escalabilidade de leitura)

```text
ANTES
EC2 → RDS Primary (Multi-AZ)

DEPOIS
                 ┌── Writer (Primary)       ← INSERT/UPDATE/DELETE
EC2 (app) ───────┤
                 └── Reader (Read Replica)  ← SELECT selecionados
```

**Ganho:** escalabilidade de leitura. Métrica de interesse: `ReplicaLag`. Diferenciação didática: **Multi-AZ = disponibilidade; Read Replica = escalabilidade de leitura.**

### Resultado alcançado (Tarefas 21–23 — escalabilidade de leitura comprovada)

A Fase 3 percorreu o ciclo **IDENTIFICAR PROBLEMA → IMPLEMENTAR → TESTAR → OBSERVAR → COMPROVAR**, encerrado na Tarefa 23 (testes de replicação). O passo a passo está no `IMPLANTACAO.md` (Passos 3.1 a 3.3) e os testes no `TESTES.md` (T3.1 e T3.2):

- **Problema atacado:** ao final da Fase 2, **toda** a carga de leitura (`SELECT`) continuava indo para a **única instância primária** — o Multi-AZ resolve disponibilidade, mas **não** escala leitura (o standby síncrono não é legível). Um pico de leituras poderia saturar o primário e degradar também as escritas.
- **Réplica criada (Tarefa 21):** a `rds-mysql-lab-replica` foi provisionada a partir de `rds-mysql-lab`, como **cópia somente leitura** com **replicação assíncrona**, vinculada ao primário como origem. Comprovou-se que a réplica **rejeita escrita** (erro `--read-only`) e **recebe os dados** do primário.
- **Roteamento leitura/escrita (Tarefa 22):** preenchendo apenas `DB_READER_ENDPOINT` no `.env` (endpoint da réplica), a aplicação passou a enviar **escritas ao writer** e **leituras de página ao reader** — **sem alteração de código** (`Config.tem_reader_dedicado()` passa a `True`). O endpoint usado é **registrado nos logs** (`Conexao de banco [WRITER]`/`[READER]`) e o painel `/database-lab` passou a exibir **"RDS MySQL — Writer + Read Replica"** com **duas conectividades OK** (writer e reader, endpoints distintos).
- **Replicação testada e `ReplicaLag` observado (Tarefa 23):** um registro escrito no **writer** (produto `Replicacao-…`) foi lido na **réplica** após um **pequeno atraso**, evidenciando a **consistência eventual** da replicação **assíncrona** (Requisito 5.7). O widget **`ReplicaLag`** do dashboard `db-lab-01-rds` — que ficava **"Sem dados"** nas Fases 1–2 por não haver réplica legível — **passou a exibir valores** (próximos de 0 em repouso; oscilando sob rajada de escritas), medindo o **atraso, em segundos, da replicação assíncrona** entre primário e réplica. Um recurso não é considerado válido só por aparecer "Disponível" — o funcionamento foi comprovado por teste (Requisito 14.4).

**Conclusão comprovada — Read Replica = escalabilidade de leitura (Requisito 5.8):** a Fase 3 adicionou um **endpoint legível** (a réplica) para o qual a aplicação direciona `SELECT`, **aliviando o primário** e escalando a capacidade de leitura. Isto **consolida a distinção** que a Fase 2 já antecipava:

| Aspecto | **Multi-AZ (Fase 2)** | **Read Replica (Fase 3)** |
|---|---|---|
| Problema que resolve | **Alta disponibilidade** (failover automático) | **Escalabilidade de leitura** |
| Replicação | **Síncrona** | **Assíncrona** (→ `ReplicaLag`) |
| Papel secundário atende leitura? | **Não** (standby em espera) | **Sim** (reader recebe `SELECT`) |
| Consistência | Forte | **Eventual** |
| `ReplicaLag` no dashboard | **"Sem dados"** | **Exibe valores** |

- A transição do widget `ReplicaLag` de **"Sem dados"** (Fase 2) para **"com dados"** (Fase 3) é a **prova concreta** dessa diferença: a métrica só existe **porque agora há uma réplica de leitura**. Multi-AZ e Read Replica são **complementares** (podem coexistir), mas resolvem **problemas diferentes**.

> **Custo (Requisito 12):** a Read Replica é **uma segunda instância** e gera custo enquanto existir. Com a Fase 3 comprovada e como a **Fase 4 (S3) não exige a réplica**, ela pode ser **excluída** para economizar — antes, **esvaziar `DB_READER_ENDPOINT`** no `.env` e reiniciar o serviço (a leitura volta ao writer, sem mudança de código). Isso evita **manter recursos caros simultaneamente** (Requisito 12.2). Guia no `IMPLANTACAO.md`, Fase 3.

---

## Fase 4 — Imagens no S3

```text
ANTES
EC2 [ app + imagens ] → RDS

DEPOIS
EC2 [ app ] → RDS
imagens → Amazon S3 (banco guarda só a referência/URL)
```

**Ganho:** arquivos deixam de depender da EC2; base para durabilidade e escalabilidade de conteúdo estático.

### Resultado alcançado (Tarefas 24–25 — imagens desacopladas da EC2)

A Fase 4 fecha a evolução do Projeto 01 movendo o **último componente de estado que ainda vivia na EC2** — as imagens dos produtos — para o **Amazon S3**. O passo a passo está no `IMPLANTACAO.md` (Fase 4) e no `scripts/upload_imagens_s3.md`, e os testes no `TESTES.md` (Fase 4):

- **Problema atacado:** desde a Fase 0, as imagens eram servidas de `static/images/` pela própria EC2. Mesmo com o banco no RDS (Fases 1–3), **os arquivos ainda dependiam da instância** — se a EC2 caísse ou fosse substituída, as imagens sumiam. Restava esse acoplamento entre conteúdo estático e compute.
- **Migração para o S3 (Tarefa 24):** criou-se um bucket S3, subiram-se os mesmos arquivos de imagem e ativou-se `STORAGE_MODE=s3` no `.env`. A partir daí, `storage.py` passa a montar a **URL/chave do objeto no S3** em vez do caminho local — **sem alterar código** (só configuração). A coluna `produtos.imagem` continua guardando **apenas a referência** (nome/chave), nunca o binário (Requisito 6.4): a troca de `local` para `s3` foi só configuração + upload dos mesmos arquivos.
- **Validação (Tarefa 25):** a loja passou a servir as imagens diretamente do S3; o painel `/database-lab` reflete a arquitetura final (EC2 + RDS + S3). Um recurso não é considerado válido só por aparecer "Disponível" — o carregamento das imagens a partir do S3 foi comprovado por teste (Requisito 14.4).

**Conclusão comprovada — arquivos independentes da EC2 (Requisito 6.5):** o conteúdo estático passou a ter **durabilidade e disponibilidade próprias** do S3, desacoplado do ciclo de vida da instância. Com isso, os três componentes de estado que começaram acoplados na EC2 estão agora em serviços gerenciados independentes: **banco no RDS**, **imagens no S3**, restando na EC2 apenas o **compute** (a aplicação Flask).

---

## Arquitetura final consolidada (Projeto 01)

```text
Usuário → Route 53 → EC2 (Flask)
                       ├── RDS MySQL (Multi-AZ)
                       │      └── Read Replica (leitura)
                       └── Amazon S3 (imagens)

Observabilidade: CloudWatch + EventBridge + CloudWatch Logs
```

Da Fase 0 (um único ponto de falha) até a arquitetura final, o Projeto 01 elimina o SPOF do banco (RDS Multi-AZ), escala leitura (Read Replica) e desacopla os arquivos (S3), aplicando na prática os princípios de **alta disponibilidade** e **tolerância a falhas**.
