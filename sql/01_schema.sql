-- ============================================================================
-- 01_schema.sql — AWS Database Lab Store (Projeto 01, Fase 0)
--
-- Objetivo: criar as TABELAS do banco `loja` no MySQL local (na EC2).
--           Modelo relacional base reaproveitado por todos os projetos.
--
-- Ordem de execução dos scripts SQL:
--   1) 00_create_database.sql   -> cria banco e usuário de aplicação
--   2) 01_schema.sql            -> cria as tabelas                       (ESTE)
--   3) 02_seed.sql              -> insere dados de exemplo
--
-- Como executar (na EC2, após 00_create_database.sql):
--   sudo mysql < 01_schema.sql
--   (ou:  mysql -u root -p < 01_schema.sql)
--
-- ----------------------------------------------------------------------------
-- Decisões de modelagem:
--   * Engine InnoDB em todas as tabelas: suporta CHAVES ESTRANGEIRAS (FK),
--     transações e integridade referencial (Requisitos 1 e 2).
--   * Charset utf8mb4 (herdado do banco) para acentuação pt-BR e emojis.
--   * A coluna `produtos.imagem` guarda apenas a REFERÊNCIA (nome do arquivo
--     ou, futuramente, a chave no S3), NUNCA o binário da imagem (Requisito 6).
--   * A ordem de criação respeita as dependências de FK: as tabelas "pai"
--     (clientes, produtos) são criadas antes das "filhas" (pedidos,
--     itens_pedido, carrinho, itens_carrinho).
--   * Os nomes de colunas seguem exatamente o que a aplicação Flask usa
--     (app.py, cart.py), garantindo compatibilidade sem adaptações.
-- ============================================================================

USE loja;

-- ----------------------------------------------------------------------------
-- Recriação idempotente: derruba as tabelas na ORDEM INVERSA das dependências
-- (primeiro as filhas, depois as pais) para permitir reexecutar este script
-- sem erros de chave estrangeira.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS itens_carrinho;
DROP TABLE IF EXISTS carrinho;
DROP TABLE IF EXISTS itens_pedido;
DROP TABLE IF EXISTS pedidos;
DROP TABLE IF EXISTS produtos;
DROP TABLE IF EXISTS clientes;

-- ----------------------------------------------------------------------------
-- clientes — cadastro de clientes da loja.
--   email UNIQUE: a aplicação depende disso para evitar duplicidade
--   (ver tratamento de erro em app.py -> salvar_cliente).
-- ----------------------------------------------------------------------------
CREATE TABLE clientes (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    nome       VARCHAR(120)  NOT NULL,
    email      VARCHAR(160)  NOT NULL,
    telefone   VARCHAR(30)   NULL,
    criado_em  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_clientes_email UNIQUE (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- produtos — catálogo de produtos.
--   preco   DECIMAL(10,2): valores monetários exatos (evita erro de ponto
--                          flutuante em preços).
--   estoque INT: quantidade disponível.
--   imagem  VARCHAR: REFERÊNCIA à imagem (nome do arquivo em static/images/
--                    na Fase 0; chave/URL do S3 na Fase 4). NUNCA o binário.
-- ----------------------------------------------------------------------------
CREATE TABLE produtos (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    nome       VARCHAR(120)   NOT NULL,
    descricao  TEXT           NULL,
    preco      DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    estoque    INT            NOT NULL DEFAULT 0,
    imagem     VARCHAR(255)   NULL,
    criado_em  TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- pedidos — cabeçalho do pedido (um pedido pertence a um cliente).
--   status: rótulo simples de estado (ex.: 'CRIADO', 'PAGO', 'ENVIADO').
--   total : valor total do pedido (DECIMAL para precisão monetária).
--   FK cliente_id -> clientes.id
--     ON DELETE RESTRICT: impede apagar um cliente que tem pedidos (integridade).
--     ON UPDATE CASCADE : propaga eventual mudança de id do cliente.
-- ----------------------------------------------------------------------------
CREATE TABLE pedidos (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id  INT            NOT NULL,
    status      VARCHAR(30)    NOT NULL DEFAULT 'CRIADO',
    total       DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    criado_em   TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pedidos_cliente
        FOREIGN KEY (cliente_id) REFERENCES clientes (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- itens_pedido — linhas de um pedido (produto + quantidade + preço na venda).
--   preco_unitario: "congela" o preço no momento da venda (não usa o preço
--                   atual do produto, que pode mudar depois).
--   FK pedido_id  -> pedidos.id   (ON DELETE CASCADE: apagar o pedido apaga
--                                   seus itens automaticamente).
--   FK produto_id -> produtos.id  (ON DELETE RESTRICT: impede apagar produto
--                                   que está em algum pedido).
-- ----------------------------------------------------------------------------
CREATE TABLE itens_pedido (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id       INT            NOT NULL,
    produto_id      INT            NOT NULL,
    quantidade      INT            NOT NULL DEFAULT 1,
    preco_unitario  DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    CONSTRAINT fk_itens_pedido_pedido
        FOREIGN KEY (pedido_id) REFERENCES pedidos (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_itens_pedido_produto
        FOREIGN KEY (produto_id) REFERENCES produtos (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- carrinho — carrinho do cliente (usado quando CART_MODE=relational).
--   No Projeto 03 o carrinho migra para o DynamoDB; estas tabelas permanecem
--   para a fase relacional (Fase 0 até o Projeto 02).
--   FK cliente_id -> clientes.id (ON DELETE CASCADE: apagar cliente apaga o
--                                 carrinho dele).
-- ----------------------------------------------------------------------------
CREATE TABLE carrinho (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id  INT        NOT NULL,
    criado_em   TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_carrinho_cliente
        FOREIGN KEY (cliente_id) REFERENCES clientes (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- itens_carrinho — itens dentro de um carrinho.
--   uq_carrinho_produto: garante no máximo UMA linha por (carrinho, produto);
--                        a aplicação incrementa a quantidade em vez de duplicar
--                        (ver cart.py -> _add_item_relacional).
--   FK carrinho_id -> carrinho.id (ON DELETE CASCADE).
--   FK produto_id  -> produtos.id (ON DELETE RESTRICT).
-- ----------------------------------------------------------------------------
CREATE TABLE itens_carrinho (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    carrinho_id  INT  NOT NULL,
    produto_id   INT  NOT NULL,
    quantidade   INT  NOT NULL DEFAULT 1,
    CONSTRAINT uq_carrinho_produto UNIQUE (carrinho_id, produto_id),
    CONSTRAINT fk_itens_carrinho_carrinho
        FOREIGN KEY (carrinho_id) REFERENCES carrinho (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_itens_carrinho_produto
        FOREIGN KEY (produto_id) REFERENCES produtos (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Validação rápida (execute manualmente após rodar este script):
--   USE loja;
--   SHOW TABLES;
--   -- Esperado: carrinho, clientes, itens_carrinho, itens_pedido,
--   --           pedidos, produtos
--   SHOW CREATE TABLE pedidos\G   -- confirma a FK para clientes
--   SHOW CREATE TABLE itens_pedido\G
-- ----------------------------------------------------------------------------
