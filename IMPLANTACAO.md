# Implantação — Da EC2 Monolítica ao RDS Resiliente: Eliminando o Ponto Único de Falha

> Passo a passo para implantar o Projeto 01 (Console AWS em pt-BR, região **us-east-1**). Foco em **onde clicar, quais campos preencher e como validar**. O raciocínio arquitetural (o "por que" de cada recurso) está no `README.md` e no `ARQUITETURA.md`.
>
> **Domínio do projeto:** `rds-lab.inhesta.net`.
> **Acesso à EC2:** SSH com a chave `.pem` — `ssh -i aws-database-lab-key.pem ec2-user@IP_PUBLICO_DA_EC2`.
> **Substitua nos comandos:** `ENDPOINT_RDS` = endpoint real do RDS; `ENDPOINT_DA_REPLICA` = endpoint da réplica; `NOME_BUCKET` = nome do bucket S3; `IP_PUBLICO` = IP público (Elastic IP) da EC2.
> **Convenção de evidências:** salve prints em `evidencias/` com nome `NN-descricao.png`.

---

## Fase 0 — Monolito em EC2 (app + MySQL local)

### 0.1 — Criar a instância EC2 (Console)

- **Caminho:** Serviços → Computação → **EC2** → **Instâncias** (Instances) → botão **Executar instâncias** (Launch instances).
- **Campos:**
  - Nome (Name): `ec2-aws-database-lab`
  - Imagem (AMI): **Amazon Linux 2023** (x86_64)
  - Tipo de instância (Instance type): `t3.micro` (Free Tier quando disponível)
  - Par de chaves (Key pair): **Criar novo par de chaves** → tipo `RSA`, formato `.pem`, nome `aws-database-lab-key` → **Baixar** o `.pem` e guardar (não versionar).
  - Configurações de rede (Network settings): **VPC padrão**; em Grupo de segurança → **Criar grupo de segurança**, nome `sg-ec2-lab`.
- **Regras de entrada do `sg-ec2-lab`:**

  | Tipo | Protocolo | Porta | Origem |
  |---|---|---|---|
  | SSH | TCP | `22` | **Meu IP** |
  | TCP personalizada | TCP | `5000` | **Meu IP** |

  Não abrir `3306` aqui. Nunca usar `0.0.0.0/0`.
- **Finalizar:** **Executar instância** (Launch instance).
- **Validar:** instância em **Em execução** (Running); SSH conecta: `ssh -i aws-database-lab-key.pem ec2-user@IP_PUBLICO`.
- **Evidência:** print da instância Running, das regras do `sg-ec2-lab` e do prompt SSH conectado.

![Descrição da imagem](<imagens/imagem%20(29).png>)

### 0.2 — Instalar o MySQL na EC2 (SSH)
```bash
sudo dnf update -y
sudo dnf install -y https://dev.mysql.com/get/mysql84-community-release-el9-1.noarch.rpm
sudo rpm --import https://repo.mysql.com/RPM-GPG-KEY-mysql-2023
sudo dnf install -y mysql-community-server
sudo systemctl enable --now mysqld
sudo systemctl status mysqld                          # deve estar active (running)
sudo grep "temporary password" /var/log/mysqld.log    # anote a senha temporaria
sudo mysql_secure_installation                        # defina senha forte do root
```

### 0.3 — Obter o código e criar banco/tabelas (SSH)
```bash
sudo dnf install -y git
cd ~ && git clone URL_DO_SEU_REPOSITORIO
cd ~/AWS-Database/aws-database-evolution-labs/01-rds-resilience/sql
# edite 00_create_database.sql e troque ALTERE_ESTA_SENHA pela senha do app_loja
sudo mysql -u root -p < 00_create_database.sql
sudo mysql -u root -p loja < 01_schema.sql
sudo mysql -u root -p loja < 02_seed.sql
mysql -u app_loja -p loja -e "SHOW TABLES; SELECT COUNT(*) FROM produtos;"   # 6 tabelas, 5 produtos
```

### 0.4 — Aplicação (venv + .env + systemd) (SSH)
```bash
sudo dnf install -y python3 python3-pip
sudo mkdir -p /opt/aws-database-lab
sudo cp -r ~/AWS-Database/aws-database-evolution-labs/01-rds-resilience/app/. /opt/aws-database-lab/
sudo cp ~/AWS-Database/aws-database-evolution-labs/01-rds-resilience/scripts/aws-database-lab.service /opt/aws-database-lab/scripts/
sudo rm -rf /opt/aws-database-lab/.venv
sudo chown -R ec2-user:ec2-user /opt/aws-database-lab
cd /opt/aws-database-lab
sudo -u ec2-user python3 -m venv .venv
sudo -u ec2-user .venv/bin/pip install --upgrade pip
sudo -u ec2-user .venv/bin/pip install -r requirements.txt   # inclui cryptography
sudo cp .env.example .env   # edite: DB_WRITER_ENDPOINT=localhost, DB_NAME=loja, DB_USER=app_loja, DB_PASSWORD=..., AWS_REGION=us-east-1
sudo chmod 600 .env
sudo cp scripts/aws-database-lab.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now aws-database-lab
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/   # 200
```
Acesse: `http://IP_PUBLICO:5000/`

### 0.5 — (Recomendado) Alocar Elastic IP (Console)

- **Caminho:** EC2 → **Enderecos IP elásticos** (Elastic IPs) → **Alocar endereço IP elástico** (Allocate) → confirmar.
- **Associar:** selecionar o IP alocado → **Ações** (Actions) → **Associar endereço IP elástico** (Associate) → Recurso: **Instância**, escolher `ec2-aws-database-lab` → **Associar**.
- **Validar:** a instância passa a exibir esse IP como **IPv4 público**; use-o como `IP_PUBLICO`.
- **Evidência:** print do Elastic IP associado à instância.

![Descrição da imagem](<imagens/imagem%20(32).png>)

### 0.6 — DNS no Route 53 (`rds-lab.inhesta.net`) (Console)

- **Caminho:** Serviços → Rede e entrega de conteúdo → **Route 53** → **Zonas hospedadas** (Hosted zones) → clicar na zona `inhesta.net` → botão **Criar registro** (Create record).
- **Campos:**
  - Nome do registro (Record name): `rds-lab` (o Console completa para `rds-lab.inhesta.net`)
  - Tipo (Record type): **A – Roteia o tráfego para um endereço IPv4**
  - Alias (Alias): **desligado** (Off)
  - Valor (Value): o **IP público / Elastic IP** da EC2 (só o IP, sem `http://` nem porta)
  - TTL: manter padrão `300`
  - Política de roteamento (Routing policy): manter **Simples**
- **Finalizar:** **Criar registros** (Create records).
- **Validar (na sua máquina):** `nslookup rds-lab.inhesta.net` → retorna o IP da EC2. Depois abra `http://rds-lab.inhesta.net:5000/`.

![Descrição da imagem](<imagens/imagem%20(33).png>)



<p align="center">
  <img src="imagens/imagem%20(4).png" width="30%" />
  <img src="imagens/imagem%20(5).png" width="30%" />
  <img src="imagens/imagem%20(6).png" width="30%" />
</p>
<p align="center">
  <img src="imagens/imagem%20(7).png" width="30%" />
  <img src="imagens/imagem%20(8).png" width="30%" />
  <img src="imagens/imagem%20(9).png" width="30%" />
</p>

---

## Fase 1 — RDS MySQL Single-AZ

### 1.1 — Security Group do banco `sg-db-lab` (Console)

- **Caminho:** EC2 → **Grupos de segurança** (Security Groups) → **Criar grupo de segurança**.
- **Campos:** Nome `sg-db-lab`; Descrição livre; VPC = a mesma da EC2 (VPC padrão).
- **Regra de entrada (Inbound):** Tipo **MYSQL/Aurora** (porta `3306`); Origem (Source): selecionar **Personalizado** e escolher o grupo **`sg-ec2-lab`** (referência de SG, não CIDR). Nunca `0.0.0.0/0`.
- **Finalizar:** **Criar grupo de segurança**.
- **Evidência:** print da regra 3306 com origem = `sg-ec2-lab`.

![Descrição da imagem](<imagens/imagem%20(30).png>)
![Descrição da imagem](<imagens/imagem%20(31).png>)



### 1.2 — Criar o RDS MySQL Single-AZ (Console)

> **ATENÇÃO DE CUSTO** — Amazon RDS. Cobra por instância enquanto existir. Use classe elegível ao Free Tier quando disponível; **pare/exclua** a instância ao terminar os testes do projeto.

- **Caminho:** Serviços → Banco de dados → **RDS** → **Bancos de dados** (Databases) → **Criar banco de dados** (Create database).
- **Campos:**
  - Método de criação: **Criação padrão** (Standard create)
  - Tipo de mecanismo (Engine type): **MySQL**; Versão: **MySQL 8.x**
  - Modelos (Templates): **Nível gratuito** (Free tier) se disponível
  - Disponibilidade (Availability): **Instância de banco de dados única** (Single-AZ)
  - Identificador (DB instance identifier): `rds-mysql-lab`
  - Nome de usuário mestre (Master username): `admin`; Gerenciamento de credenciais: **Autogerenciado**, definir a senha mestre (anotar fora do Git)
  - Classe (DB instance class): `db.t3.micro`
  - Armazenamento: **gp3** (padrão)
  - Conectividade (Connectivity): VPC padrão; **Acesso público (Public access) = Não**; Grupo de segurança da VPC: **escolher existente** → `sg-db-lab` (remover o default)
  - Configuração adicional (Additional configuration): Nome do banco de dados inicial (Initial database name): `loja`
- **Finalizar:** **Criar banco de dados**.
- **Validar:** aguardar estado **Disponível** (Available); copiar o **Endpoint** (aba Conectividade e segurança).
- **Evidência:** print do RDS Disponível com o endpoint visível.

### 1.3 — Migrar dados e criar usuário no RDS (SSH)
```bash
nc -zv ENDPOINT_RDS 3306                          # se faltar nc: sudo dnf install -y nmap-ncat
cd ~ && mysqldump --single-transaction --routines --triggers --no-create-db -u root -p loja > loja_dump.sql
mysql -h ENDPOINT_RDS -u admin -p loja < loja_dump.sql
cd ~/AWS-Database/aws-database-evolution-labs/01-rds-resilience/sql
# edite 03_create_app_user_rds.sql (senha do app_loja = mesma do .env)
mysql -h ENDPOINT_RDS -u admin -p < 03_create_app_user_rds.sql
mysql -h ENDPOINT_RDS -u app_loja -p loja -e "SELECT 1;"   # conexao_ok
```

### 1.4 — Apontar a app para o RDS (SSH)
```bash
sudo cp /opt/aws-database-lab/.env /opt/aws-database-lab/.env.fase0.bak
sudo nano /opt/aws-database-lab/.env
#   DB_WRITER_ENDPOINT=ENDPOINT_RDS
#   DB_READER_ENDPOINT=            (vazio)
#   LAB_ARCH_VERSION=Fase 1 — RDS Single-AZ
sudo systemctl restart aws-database-lab
curl -s http://localhost:5000/database-lab | grep -iE "RDS|Single-AZ"
```
![Descrição da imagem](<imagens/imagem%20(11).png>)

---

## Observabilidade (Console, região us-east-1)

### Dashboard `db-lab-01-rds`
- **Caminho:** **CloudWatch** → **Painéis** (Dashboards) → **Criar painel** (Create dashboard) → nome `db-lab-01-rds`.
- **Widgets:** **Adicionar widget** → **Linha** (Line) → métricas em **RDS → Por DBInstanceIdentifier** → selecionar `rds-mysql-lab`. Adicionar: `CPUUtilization`, `DatabaseConnections`, `FreeStorageSpace`, `ReadLatency`, `WriteLatency`, `ReadIOPS`, `WriteIOPS`, `ReplicaLag`.
- **Salvar** o painel.

![Descrição da imagem](<imagens/imagem%20(11).png>)

### Alarme `db-lab-01-rds-cpu-alta`
- **Caminho:** CloudWatch → **Alarmes** (Alarms) → **Criar alarme** → **Selecionar métrica** → RDS → `rds-mysql-lab` → `CPUUtilization`.
- **Condição:** Limite estático, **Maior que 70%**, por ~2 períodos de 1 min.
- **Notificação:** opcional (SNS). Nome: `db-lab-01-rds-cpu-alta`.

![Descrição da imagem](<imagens/imagem%20(17).png>)

![Descrição da imagem](<imagens/imagem%20(16).png>)


### Log Group + Regra do EventBridge
- **Log Group:** CloudWatch → **Logs** → **Grupos de logs** → **Criar grupo de logs** → nome `/aws/events/db-lab-01-rds`, retenção `30 dias`.
- **Regra:** **EventBridge** → **Regras** (Rules) → **Criar regra** → nome `db-lab-01-rds-eventos`; Tipo: **Regra com padrão de evento**.
  - Padrão de evento: Origem (Source) `aws.rds`; Tipo de detalhe (Detail type) **RDS DB Instance Event**; categorias `failover, failure, availability, maintenance`.
  - Destino (Target): **Grupo de logs do CloudWatch** → `/aws/events/db-lab-01-rds`.
- **Validar:** o Log Group fica vazio até ocorrer um evento (normal); será populado no failover da Fase 2.

![Descrição da imagem](<imagens/imagem%20(20).png>)
![Descrição da imagem](<imagens/imagem%20(21).png>)
![Descrição da imagem](<imagens/imagem%20(22).png>)
![Descrição da imagem](<imagens/imagem%20(23).png>)
![Descrição da imagem](<imagens/imagem%20(13).png>)

---

## Fase 2 — Multi-AZ (failover)

> **ATENÇÃO DE CUSTO** — Multi-AZ **dobra** o custo de instância (primário + standby). Reverter para Single-AZ após comprovar.

### 2.1 — Converter para Multi-AZ (Console)
- **Caminho:** RDS → **Bancos de dados** → `rds-mysql-lab` → **Modificar** (Modify).
- **Campo:** Disponibilidade e durabilidade → **Criar uma instância em espera** (Multi-AZ DB instance).
- **Aplicar:** ao final, escolher **Aplicar imediatamente** (Apply immediately) → **Modificar instância de banco de dados**.
- **Validar:** instância passa a **Modificando** e volta a **Disponível**; aba **Configuração** mostra **Multi-AZ = Sim** e duas AZs (primária + em espera). A loja segue funcionando pelo mesmo endpoint (`/database-lab` = WRITER OK).
- **Evidência:** print da aba Configuração (Multi-AZ = Sim, AZ primária + secundária).

### 2.2 — Medir o failover (SSH)
```bash
ENDPOINT_RDS="..."; read -s -p "Senha app_loja: " DB_PASSWORD; echo
while true; do ts=$(date "+%H:%M:%S"); \
  if mysql -h "$ENDPOINT_RDS" -u app_loja -p"$DB_PASSWORD" loja -N -e "SELECT 1;" >/dev/null 2>&1; \
  then echo "$ts OK"; else echo "$ts FALHA"; fi; sleep 1; done
```

### 2.3 — Provocar e comprovar
- **Provocar (Console):** RDS → `rds-mysql-lab` → **Ações** (Actions) → **Reiniciar com failover** (Reboot with failover). Anote o horário do disparo.
- **Observar:** o loop mostra `OK → FALHA → OK` (tempo de recuperação).
- **Comprovar:** evento `failover` em CloudWatch → Logs → `/aws/events/db-lab-01-rds` + aba **Eventos** do RDS + degrau no painel `db-lab-01-rds`.
- **Evidência:** print do loop, do evento no Log Group e do degrau nas métricas.
- **Custo:** após comprovar, reverter para Single-AZ (Modificar → **Instância única** → aplicar imediatamente).

---

## Fase 3 — Read Replica

> **ATENÇÃO DE CUSTO** — a réplica é uma **segunda instância** e cobra enquanto existir. Excluir após comprovar.

### 3.1 — Criar a réplica (Console)
- **Caminho:** RDS → `rds-mysql-lab` → **Ações** (Actions) → **Criar réplica de leitura** (Create read replica).
- **Campos:** Identificador da réplica: `rds-mysql-lab-replica`; classe `db.t3.micro`; **Acesso público = Não**; manter demais padrões.
- **Finalizar:** **Criar réplica de leitura**.
- **Validar:** aguardar a réplica ficar **Disponível**; copiar o **endpoint da réplica**.

![Descrição da imagem](<imagens/imagem%20(24).png>)
![Descrição da imagem](<imagens/imagem%20(25).png>)
![Descrição da imagem](<imagens/imagem%20(26).png>)
![Descrição da imagem](<imagens/imagem%20(14).png>)

### 3.2 — Rotear leitura na app (SSH)
```bash
sudo nano /opt/aws-database-lab/.env
#   DB_READER_ENDPOINT=ENDPOINT_DA_REPLICA   (uma unica linha, sem duplicar)
#   LAB_ARCH_VERSION=Fase 3 — RDS Read Replica
sudo systemctl restart aws-database-lab
curl -s http://localhost:5000/database-lab | grep -iE "Writer|Reader"   # WRITER e READER
curl -s -o /dev/null http://localhost:5000/produtos                      # leitura -> READER
curl -s -o /dev/null -X POST http://localhost:5000/produtos/salvar --data "nome=Teste&preco=10&estoque=1"  # escrita -> WRITER
sudo journalctl -u aws-database-lab -n 40 --no-pager | grep -i "Conexao de banco"
```
- **Comprovar (Console):** painel `db-lab-01-rds` → widget `ReplicaLag` passa a exibir dados.
- **Evidência:** log com `[WRITER]`/`[READER]` e print do `ReplicaLag` com dados.
- **Custo:** após comprovar, esvaziar `DB_READER_ENDPOINT` no `.env`, reiniciar o serviço e **excluir a réplica** (RDS → réplica → Ações → Excluir).

---

## Fase 4 — Imagens no S3

> **ATENÇÃO DE CUSTO** — S3 (armazenamento + requisições). Para SVGs é ínfimo; pode manter.

### 4.1 — Criar o bucket (Console)
- **Caminho:** Serviços → Armazenamento → **S3** → **Criar bucket** (Create bucket).
- **Campos:** Nome (globalmente único): `NOME_BUCKET`; Região: **us-east-1**.
- **Acesso público:** para servir imagens publicamente, **desmarcar** "Bloquear todo o acesso público" (Block all public access) e confirmar o aviso; depois adicionar uma **política de bucket** permitindo `s3:GetObject` nos objetos.
- **Finalizar:** **Criar bucket**.
- **Evidência:** print do bucket criado e da política aplicada.

![Descrição da imagem](<imagens/imagem%20(35).png>)
![Descrição da imagem](<imagens/imagem%20(36).png>)
![Descrição da imagem](<imagens/imagem%20(37).png>)
![Descrição da imagem](<imagens/imagem%20(38).png>)
![Descrição da imagem](<imagens/imagem%20(34).png>)

### 4.2 — IAM Role para a EC2 acessar o S3 (Console)
- **Caminho:** Serviços → Segurança → **IAM** → **Funções** (Roles) → **Criar função** (Create role).
- **Entidade confiável:** **Serviço da AWS** (AWS service) → **EC2**.
- **Permissões:** criar/anexar política com `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` no `arn:aws:s3:::NOME_BUCKET` (e `/*`). Nome da função: `role-ec2-s3-lab`.
- **Anexar à EC2:** EC2 → `ec2-aws-database-lab` → **Ações** (Actions) → **Segurança** (Security) → **Modificar função do IAM** (Modify IAM role) → escolher `role-ec2-s3-lab`.
- **Evidência:** print da role anexada à instância.

### 4.3 — Upload e ativação (SSH)
```bash
cd /opt/aws-database-lab
aws s3 sync static/images/ s3://NOME_BUCKET/ --exclude "*" --include "*.svg" --content-type "image/svg+xml"
aws s3 ls s3://NOME_BUCKET/
curl -s -o /dev/null -w "%{http_code}\n" https://NOME_BUCKET.s3.us-east-1.amazonaws.com/notebook.svg   # 200 (403 = falta leitura publica)
sudo nano /opt/aws-database-lab/.env
#   STORAGE_MODE=s3
#   S3_BUCKET=NOME_BUCKET
#   S3_REGION=us-east-1
#   LAB_ARCH_VERSION=Fase 4 — Imagens no S3
sudo systemctl restart aws-database-lab
curl -s http://localhost:5000/ | grep -o "src=\"[^\"]*notebook[^\"]*\"" | head -1   # URL do S3
```

---

## (Opcional) Acesso pela porta 80 — Nginx como proxy reverso
```bash
sudo dnf install -y nginx
sudo tee /etc/nginx/conf.d/aws-database-lab.conf > /dev/null <<EOF
server { listen 80; server_name _; location / { proxy_pass http://127.0.0.1:5000; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; } }
EOF
sudo setsebool -P httpd_can_network_connect 1     # essencial no AL2023 (senao da 502)
sudo systemctl enable --now nginx
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:80/   # 200
```
No `sg-ec2-lab` (Console), adicionar regra de entrada **HTTP (TCP 80)** com origem **Meu IP**. Depois acesse `http://rds-lab.inhesta.net/`.

---

## Armadilhas comuns (erros reais desta implantação)

| Sintoma | Causa | Correção |
|---|---|---|
| `Internal Server Error` (500), log cita `cryptography ... caching_sha2_password` | pacote `cryptography` ausente no venv | `sudo -u ec2-user /opt/aws-database-lab/.venv/bin/pip install cryptography` e reiniciar (já está no `requirements.txt`) |
| `gunicorn: command not found` / `ModuleNotFoundError: pymysql` | `pip install` rodou fora do venv | usar caminho absoluto `.venv/bin/pip install -r requirements.txt` |
| `nc: command not found` | AL2023 sem netcat | `sudo dnf install -y nmap-ncat` |
| `Access denied ...@'localhost'` ao conectar no RDS | variável de endpoint vazia (cai em localhost) | definir `ENDPOINT_RDS` na sessão; variáveis somem a cada nova sessão |
| `Access denied ...@'<IP>'` | senha errada ou `app_loja@'%'` não criado no RDS | rodar `03_create_app_user_rds.sql` e usar a mesma senha do `.env` |
| cliente `mysql` fica pedindo senha | usou `-p senha` (com espaço) | usar senha colada: `-p"$DB_PASSWORD"` |
| `journalctl` retorna `-- No entries --` | usuário sem privilégio de log | usar `sudo journalctl -u aws-database-lab` |
| painel só mostra WRITER (sem READER) | `DB_READER_ENDPOINT` só no shell, não no `.env` (ou linha duplicada) | editar o `.env`, uma única linha, e reiniciar |
| app não sobe após reboot | `mysqld` não habilitado no boot | `sudo systemctl enable --now mysqld` |
| navegador não abre na porta 80 | Nginx não configurado / SELinux | configurar Nginx + `setsebool httpd_can_network_connect 1` |
| imagens não vêm do S3 | `STORAGE_MODE` ainda `local` | ajustar `STORAGE_MODE=s3` no `.env` e reiniciar |
| `403` ao abrir a imagem pela URL do S3 | objetos sem leitura pública | ajustar Block Public Access + política de bucket com `s3:GetObject` |
| DNS não resolve `rds-lab.inhesta.net` | registro recém-criado / TTL | aguardar até ~5 min e repetir `nslookup` |

---

## Redução de custo / limpeza

Para **reverter, parar ou excluir** os recursos ao pausar ou encerrar o Projeto 01 (Multi-AZ, Read Replica, RDS, EC2, Elastic IP), siga o **`EXCLUSAO.md`**.
