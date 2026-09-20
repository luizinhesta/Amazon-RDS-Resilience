-- ============================================================================
-- 00_create_database.sql — AWS Database Lab Store (Projeto 01, Fase 0)
--
-- Objetivo: criar o banco de dados `loja` e o usuário de aplicação `app_loja`
--           usado pela aplicação Flask para conectar ao MySQL local (na EC2).
--
-- Ordem de execução dos scripts SQL:
--   1) 00_create_database.sql   -> cria banco e usuário de aplicação  (ESTE)
--   2) 01_schema.sql            -> cria as tabelas
--   3) 02_seed.sql              -> insere dados de exemplo
--
-- Como executar (na EC2, após instalar o MySQL Server):
--   sudo mysql < 00_create_database.sql
--   (ou, se o root do MySQL tiver senha:  mysql -u root -p < 00_create_database.sql)
--
-- ----------------------------------------------------------------------------
-- SEGURANÇA (Requisito 11):
--   * A aplicação NÃO usa o usuário root do MySQL. Ela usa `app_loja`, que tem
--     privilégios APENAS sobre o banco `loja`.
--   * A senha abaixo é apenas um PLACEHOLDER. TROQUE por uma senha forte antes
--     de executar em qualquer ambiente e use a MESMA senha na variável de
--     ambiente DB_PASSWORD do arquivo `.env` da aplicação.
--   * NUNCA versione a senha real no Git. O `.env` fica fora do controle de
--     versão (ver .gitignore).
-- ============================================================================

-- 1) Banco de dados da loja.
--    utf8mb4 garante suporte completo a acentuação (pt-BR) e emojis.
CREATE DATABASE IF NOT EXISTS loja
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 2) Usuário de aplicação.
--    IMPORTANTE: troque 'ALTERE_ESTA_SENHA' por uma senha forte real.
--    Em MySQL 8 (Amazon Linux 2023), o autenticador padrão é caching_sha2_password.
--    Mantemos o padrão do servidor. Caso seu driver exija, veja a nota ao final.
CREATE USER IF NOT EXISTS 'app_loja'@'localhost'
    IDENTIFIED BY 'ALTERE_ESTA_SENHA';

-- 3) Privilégios: conceder acesso APENAS ao banco `loja` (menor privilégio).
--    Evitamos GRANT ALL em *.* — o usuário de aplicação não administra o servidor.
GRANT SELECT, INSERT, UPDATE, DELETE
    ON loja.*
    TO 'app_loja'@'localhost';

-- 4) Aplicar as mudanças de privilégios.
FLUSH PRIVILEGES;

-- ----------------------------------------------------------------------------
-- Validação rápida (execute manualmente após rodar este script):
--   SHOW DATABASES LIKE 'loja';
--   SELECT user, host FROM mysql.user WHERE user = 'app_loja';
--   SHOW GRANTS FOR 'app_loja'@'localhost';
--
-- Teste de login do usuário de aplicação:
--   mysql -u app_loja -p loja -e "SELECT 1 AS conexao_ok;"
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- NOTA (compatibilidade de driver):
--   A aplicação usa PyMySQL, que é compatível com caching_sha2_password do
--   MySQL 8. Portanto NÃO é necessário alterar o método de autenticação.
--   Se, em algum ambiente antigo, o driver não suportar caching_sha2_password,
--   é possível trocar o autenticador do usuário para mysql_native_password:
--
--     ALTER USER 'app_loja'@'localhost'
--         IDENTIFIED WITH mysql_native_password BY 'ALTERE_ESTA_SENHA';
--     FLUSH PRIVILEGES;
--
--   Use isso apenas se realmente necessário.
-- ----------------------------------------------------------------------------
