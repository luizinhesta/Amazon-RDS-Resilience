-- ============================================================================
-- 02_seed.sql — AWS Database Lab Store (Projeto 01, Fase 0)
--
-- Objetivo: inserir DADOS DE EXEMPLO no banco `loja` (Requisitos 1 e 2).
--           5 produtos, 3 clientes e 2 pedidos com itens.
--
-- Ordem de execução dos scripts SQL:
--   1) 00_create_database.sql   -> cria banco e usuário de aplicação
--   2) 01_schema.sql            -> cria as tabelas
--   3) 02_seed.sql              -> insere dados de exemplo               (ESTE)
--
-- Como executar (na EC2, após 01_schema.sql):
--   sudo mysql < 02_seed.sql
--   (ou:  mysql -u root -p < 02_seed.sql)
--
-- ----------------------------------------------------------------------------
-- Observações importantes:
--   * SOBRE AS IMAGENS (coluna produtos.imagem):
--       A partir da Tarefa 5, os arquivos de imagem de exemplo já existem em
--       static/images/ (formato SVG, leve e versionável):
--         notebook.svg, mouse.svg, teclado.svg, monitor.svg, headset.svg.
--       Por isso, cada produto recebe o NOME DO ARQUIVO correspondente na
--       coluna `imagem` (apenas a REFERÊNCIA, nunca o binário — Requisito 6).
--       O storage.py, no modo STORAGE_MODE=local, monta a URL como
--       "images/<nome>" e o Flask serve o arquivo de static/images/.
--       Se algum produto ficar com `imagem` NULL/vazia, o storage.py usa
--       automaticamente o fallback `sem-imagem.svg` (ver IMAGEM_PADRAO em
--       storage.py), de modo que a loja nunca exibe "imagem quebrada".
--
--   * O cliente de id = 1 (Ana Souza) é importante: a aplicação usa
--     CLIENTE_PADRAO_CARRINHO = 1 (ver app.py) como dono do carrinho na Fase 0.
--
--   * A ordem de inserção respeita as chaves estrangeiras: primeiro clientes
--     e produtos (pais), depois pedidos e itens_pedido (filhos).
--
--   * Reexecução: os DELETE no início limpam os dados anteriores e o
--     ALTER TABLE ... AUTO_INCREMENT = 1 reinicia os ids, garantindo que os
--     ids de exemplo (clientes 1..3, produtos 1..5) fiquem estáveis a cada
--     reexecução deste seed.
-- ============================================================================

USE loja;

-- ----------------------------------------------------------------------------
-- Limpeza para reexecução idempotente do seed.
-- Ordem inversa das dependências (filhos antes dos pais).
-- ----------------------------------------------------------------------------
DELETE FROM itens_carrinho;
DELETE FROM carrinho;
DELETE FROM itens_pedido;
DELETE FROM pedidos;
DELETE FROM produtos;
DELETE FROM clientes;

-- Reinicia os contadores AUTO_INCREMENT para ids previsíveis no seed.
ALTER TABLE clientes       AUTO_INCREMENT = 1;
ALTER TABLE produtos       AUTO_INCREMENT = 1;
ALTER TABLE pedidos        AUTO_INCREMENT = 1;
ALTER TABLE itens_pedido   AUTO_INCREMENT = 1;
ALTER TABLE carrinho       AUTO_INCREMENT = 1;
ALTER TABLE itens_carrinho AUTO_INCREMENT = 1;

-- ----------------------------------------------------------------------------
-- CLIENTES (3 exemplos). O id=1 é o dono do carrinho padrão da Fase 0.
-- ----------------------------------------------------------------------------
INSERT INTO clientes (id, nome, email, telefone) VALUES
    (1, 'Ana Souza',      'ana.souza@exemplo.com',      '+55 11 90000-0001'),
    (2, 'Bruno Lima',     'bruno.lima@exemplo.com',     '+55 21 90000-0002'),
    (3, 'Carla Menezes',  'carla.menezes@exemplo.com',  '+55 31 90000-0003');

-- ----------------------------------------------------------------------------
-- PRODUTOS (5 exemplos: Notebook, Mouse, Teclado, Monitor, Headset).
-- Coluna `imagem` = nome do arquivo SVG em static/images/ (apenas referência).
-- Preços e estoques são fictícios, apenas para demonstração.
-- ----------------------------------------------------------------------------
INSERT INTO produtos (id, nome, descricao, preco, estoque, imagem) VALUES
    (1, 'Notebook', 'Notebook 14" com 16GB de RAM e SSD de 512GB.', 4599.90, 10, 'notebook.svg'),
    (2, 'Mouse',    'Mouse óptico sem fio, 1600 DPI.',                89.90, 50, 'mouse.svg'),
    (3, 'Teclado',  'Teclado mecânico ABNT2 com iluminação.',        249.90, 30, 'teclado.svg'),
    (4, 'Monitor',  'Monitor 24" Full HD IPS 75Hz.',                 899.90, 15, 'monitor.svg'),
    (5, 'Headset',  'Headset com microfone e cancelamento de ruído.',319.90, 25, 'headset.svg');

-- ----------------------------------------------------------------------------
-- Alternativa idempotente: se o INSERT acima já tiver sido executado com
-- `imagem` NULL (versão anterior deste seed), o UPDATE abaixo preenche as
-- referências pelo nome do produto sem precisar recriar as linhas. Reexecutar
-- este bloco é seguro (apenas regrava o mesmo valor).
-- ----------------------------------------------------------------------------
UPDATE produtos SET imagem = 'notebook.svg' WHERE nome = 'Notebook';
UPDATE produtos SET imagem = 'mouse.svg'    WHERE nome = 'Mouse';
UPDATE produtos SET imagem = 'teclado.svg'  WHERE nome = 'Teclado';
UPDATE produtos SET imagem = 'monitor.svg'  WHERE nome = 'Monitor';
UPDATE produtos SET imagem = 'headset.svg'  WHERE nome = 'Headset';

-- ----------------------------------------------------------------------------
-- PEDIDOS (2 exemplos) + ITENS DE PEDIDO.
--
-- Pedido 1 (cliente Ana): 1 Notebook + 1 Mouse.
--   total = 4599.90 + 89.90 = 4689.80
-- Pedido 2 (cliente Bruno): 2 Teclados + 1 Monitor.
--   total = (2 * 249.90) + 899.90 = 1399.70
--
-- O total é gravado no cabeçalho do pedido (mesma lógica de app.py -> criar_pedido).
-- preco_unitario "congela" o preço do produto no momento da venda.
-- ----------------------------------------------------------------------------
INSERT INTO pedidos (id, cliente_id, status, total) VALUES
    (1, 1, 'CRIADO', 4689.80),
    (2, 2, 'PAGO',   1399.70);

INSERT INTO itens_pedido (pedido_id, produto_id, quantidade, preco_unitario) VALUES
    -- Itens do Pedido 1
    (1, 1, 1, 4599.90),   -- 1x Notebook
    (1, 2, 1,   89.90),   -- 1x Mouse
    -- Itens do Pedido 2
    (2, 3, 2,  249.90),   -- 2x Teclado
    (2, 4, 1,  899.90);   -- 1x Monitor

-- ----------------------------------------------------------------------------
-- Validação rápida (execute manualmente após rodar este script):
--   USE loja;
--   SELECT COUNT(*) AS total_produtos FROM produtos;   -- esperado: 5
--   SELECT COUNT(*) AS total_clientes FROM clientes;   -- esperado: 3
--   SELECT COUNT(*) AS total_pedidos  FROM pedidos;    -- esperado: 2
--
--   -- Confere o total do pedido 1 a partir dos itens (deve bater com 4689.80):
--   SELECT p.id, p.total,
--          SUM(ip.quantidade * ip.preco_unitario) AS total_calculado
--   FROM pedidos p
--   JOIN itens_pedido ip ON ip.pedido_id = p.id
--   GROUP BY p.id, p.total;
--
--   -- Confere as referências de imagem (esperado: cada produto com seu .svg):
--   SELECT id, nome, imagem FROM produtos ORDER BY id;
--   -- Notebook->notebook.svg, Mouse->mouse.svg, Teclado->teclado.svg,
--   -- Monitor->monitor.svg, Headset->headset.svg. Nenhum deve ficar NULL.
-- ----------------------------------------------------------------------------
