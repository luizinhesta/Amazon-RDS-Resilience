# Exclusão / Limpeza — Da EC2 Monolítica ao RDS Resiliente: Eliminando o Ponto Único de Falha

> O que **reverter, excluir ou parar** ao pausar ou encerrar o Projeto 01, para não pagar por recursos ociosos (Requisito 12). Reaproveita o que o Projeto 02 vai usar e desliga o que foi criado só para os testes.
>
> Substitua os placeholders (`ENDPOINT_RDS`, `NOME_BUCKET`, `IP_PUBLICO`) pelos valores reais do seu ambiente.

## Princípios

- **Ao terminar cada teste, informar o que pode ser removido** (Req. 12.3). Multi-AZ e Read Replica já cumprem seu papel didático assim que o failover e o `ReplicaLag` são comprovados (Fases 2 e 3).
- **Não manter recursos caros ligados sem uso** (Req. 12.2): Multi-AZ dobra o custo de instância; a Read Replica é uma segunda instância.
- Reverter é **só configuração** — o `.env` volta a leitura ao writer sem alterar código.

---

## Sequência de limpeza

### 1. Read Replica — EXCLUIR (após comprovar a Fase 3)

A réplica (`rds-mysql-lab-replica`) é uma **segunda instância cobrada por hora**. Depois de comprovar o roteamento e o `ReplicaLag` (T3.1/T3.2), remova-a.

- **Antes:** esvaziar o reader no `.env` para a leitura voltar ao writer:
  ```bash
  sudo nano /opt/aws-database-lab/.env
  #   DB_READER_ENDPOINT=            (vazio ou comentado com #)
  sudo systemctl restart aws-database-lab
  curl -s http://localhost:5000/database-lab | grep -i "WRITER OK"
  ```
- **Excluir:** RDS → `rds-mysql-lab-replica` → **Ações → Excluir** (sem snapshot — réplica é descartável).

### 2. Multi-AZ — REVERTER para Single-AZ (após comprovar a Fase 2)

Multi-AZ paga primário + standby. Comprovado o failover (T2.0–T2.2), reverta.

- RDS → `rds-mysql-lab` → **Modificar** → Disponibilidade e durabilidade → **Instância de banco de dados única** (Single-AZ) → **Aplicar imediatamente**.
- **Validar:** aba Configuração mostra **Multi-AZ = Não**; a loja segue no mesmo endpoint.

### 3. RDS `rds-mysql-lab` — PARAR ou manter mínimo

- **Vai usar em breve:** manter **Single-AZ** ligado (writer único).
- **Não vai usar por alguns dias:** RDS → `rds-mysql-lab` → **Ações → Parar temporariamente** (até 7 dias; religa sozinho). Não paga compute, mas o **armazenamento continua cobrado**.
- **Vai migrar para o Aurora (Projeto 02):** manter ligado como origem da migração; a exclusão do RDS com snapshot final é feita no Projeto 02, após validar a migração.

### 4. EC2 — PARAR quando não estiver estudando

- EC2 → `ec2-aws-database-lab` → **Ações → Estado da instância → Parar**. O disco EBS continua cobrado; ao voltar, **Iniciar**.
- Sem Elastic IP, o IP público muda a cada start/stop — atualizar o registro DNS no Route 53.

### 5. Elastic IP — LIBERAR se não for reusar

- Um Elastic IP **associado a instância em execução** não gera custo relevante; **ocioso** (instância parada ou EIP não associado) **é cobrado**.
- Se for parar a EC2 por muito tempo: EC2 → **IPs elásticos** → selecionar → **Ações → Liberar endereços IP elásticos**.

### 6. S3 — MANTER

- Custo ínfimo para os SVGs. Pode manter (é reaproveitado no Projeto 02).

---

## Observabilidade e DNS

- **Dashboard, alarme, Log Group e regra EventBridge** (`db-lab-01-rds`, `/aws/events/db-lab-01-rds`) têm custo baixíssimo e o **padrão é reaproveitado** no Projeto 02. Não precisam ser removidos entre projetos.
- **Route 53** (zona + registro `rds-lab`): custo desprezível; pode coexistir com o `aurora-lab` do Projeto 02.

---

## Estado-alvo ao encerrar o Projeto 01

**RDS Single-AZ (writer único) + imagens no S3**, com **Multi-AZ revertido** e **Read Replica excluída** (`DB_READER_ENDPOINT` vazio). Nessa configuração o painel `/database-lab` exibe "RDS MySQL — Single-AZ" + "Amazon S3", a loja segue 100% funcional e o ambiente fica pronto para o Projeto 02 (migração para o Aurora) sem manter recursos redundantes ligados.
