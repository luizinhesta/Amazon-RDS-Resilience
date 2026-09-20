-- ============================================================================
-- 03_create_app_user_rds.sql — AWS Database Lab Store (Projeto 01, Fase 1)
--
-- Objetivo: criar, DENTRO DO RDS MySQL, o usuário de aplicação `app_loja`
--           que a aplicação Flask usará para conectar ao banco `loja` do RDS
--           SEM usar o usuário mestre `admin` (menor privilégio — Requisito 11).
--
-- Contexto (por que este script é diferente do 00_create_database.sql):
--   * No MySQL local (Fase 0) o usuário era `app_loja@'localhost'`, porque a
--     aplicação e o banco ficavam na MESMA máquina (a EC2). O host `localhost`
--     só casa com conexões vindas da própria máquina do servidor MySQL.
--   * No RDS, a aplicação conecta pela REDE (a EC2 é um host DIFERENTE do
--     servidor de banco). Um usuário `app_loja@'localhost'` NUNCA autenticaria
--     a partir da EC2, pois a conexão não parte do host do banco. Por isso
--     criamos `app_loja@'%'` (qualquer host) — o isolamento de rede é feito
--     pelo Security Group `sg-db-lab` (só a EC2, via `sg-ec2-lab`, alcança a
--     porta 3306), não pelo host do usuário MySQL.
--   * O banco `loja` já é criado pelo próprio RDS (campo "Nome inicial do banco
--     de dados" na criação da instância — Tarefa 14). Este script NÃO cria o
--     database; apenas cria o usuário de aplicação e concede privilégios.
--
-- Como executar (a partir da EC2, conectado ao RDS como usuário mestre):
--   mysql -h <ENDPOINT-DO-RDS> -u admin -p < 03_create_app_user_rds.sql
--   (o -p sem valor faz o cliente pedir a senha do `admin` de forma segura)
--
-- ----------------------------------------------------------------------------
-- SEGURANÇA (Requisito 11):
--   * A senha abaixo é apenas um PLACEHOLDER. TROQUE por uma senha forte real
--     ANTES de executar e use a MESMA senha na variável de ambiente
--     DB_PASSWORD do arquivo `.env` da aplicação (Tarefa 16).
--   * NUNCA versione a senha real no Git (o `.env` fica fora do controle de
--     versão — ver .gitignore).
--   * `app_loja` recebe privilégios APENAS no banco `loja` (não administra o
--     servidor). O usuário mestre `admin` deve ser usado só para administração,
--     nunca pela aplicação.
--   * Opção mais restrita (recomendada quando o IP interno da EC2 é estável):
--     em vez de `'%'`, use o host/sub-rede privada da EC2, por exemplo
--     `app_loja'@'10.0.%'`. Comece com `'%'` (o SG já isola o acesso) e
--     aperte o host depois, se desejar.
-- ============================================================================

-- 1) Usuário de aplicação para conexões vindas da EC2 (pela rede).
--    IMPORTANTE: troque 'ALTERE_ESTA_SENHA' por uma senha forte real.
--    Em MySQL 8, o autenticador padrão é caching_sha2_password; o PyMySQL é
--    compatível, então mantemos o padrão do servidor.
CREATE USER IF NOT EXISTS 'app_loja'@'%'
    IDENTIFIED BY 'ALTERE_ESTA_SENHA';

-- 2) Privilégios: acesso APENAS ao banco `loja` (menor privilégio).
--    Sem GRANT ALL em *.* — a aplicação não administra o servidor RDS.
GRANT SELECT, INSERT, UPDATE, DELETE
    ON loja.*
    TO 'app_loja'@'%';

-- 3) Aplicar as mudanças de privilégios.
FLUSH PRIVILEGES;

-- ----------------------------------------------------------------------------
-- Validação rápida (execute manualmente, ainda conectado como `admin`):
--   SELECT user, host FROM mysql.user WHERE user = 'app_loja';   -- espera host = %
--   SHOW GRANTS FOR 'app_loja'@'%';                              -- só sobre loja.*
--
-- Teste de login do usuário de aplicação a partir da EC2 (nova sessão):
--   mysql -h <ENDPOINT-DO-RDS> -u app_loja -p loja -e "SELECT 1 AS conexao_ok;"
--   -- Resultado esperado: uma linha com conexao_ok = 1.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- NOTA (compatibilidade de driver):
--   A aplicação usa PyMySQL, compatível com caching_sha2_password do MySQL 8;
--   NÃO é necessário alterar o método de autenticação. Se, em algum caso raro,
--   o driver não suportar, é possível trocar o autenticador:
--
--     ALTER USER 'app_loja'@'%'
--         IDENTIFIED WITH mysql_native_password BY 'ALTERE_ESTA_SENHA';
--     FLUSH PRIVILEGES;
--
--   Use isso apenas se realmente necessário.
-- ----------------------------------------------------------------------------
