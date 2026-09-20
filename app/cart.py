"""
cart.py — Abstração de carrinho de compras.

A interface pública é a MESMA independentemente do backend:
    - add_item(cliente_id, produto_id, quantidade)
    - get_cart(cliente_id)
    - remove_item(cliente_id, produto_id)
    - clear_cart(cliente_id)

Backends:
- CART_MODE=relational (Fase 0..Projeto 02): usa as tabelas relacionais
  `carrinho` e `itens_carrinho`.
- CART_MODE=dynamodb (Projeto 03+): usa a tabela DynamoDB `carrinho-lab`.

Manter a interface estável permite trocar o backend (relacional -> DynamoDB)
sem alterar as rotas Flask nem os templates.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

import db
from config import Config

logger = logging.getLogger("cart")


# ---------------------------------------------------------------------------
# Backend RELACIONAL (ativo na Fase 0)
# ---------------------------------------------------------------------------
def _garantir_carrinho_relacional(cliente_id: int) -> int:
    """
    Garante que existe um carrinho para o cliente e devolve o id do carrinho.

    Cria um carrinho novo caso ainda não exista.
    """
    linha = db.executar_leitura_um(
        "SELECT id FROM carrinho WHERE cliente_id = %s ORDER BY id DESC LIMIT 1",
        (cliente_id,),
    )
    if linha:
        return linha["id"]
    return db.executar_escrita(
        "INSERT INTO carrinho (cliente_id) VALUES (%s)",
        (cliente_id,),
    )


def _add_item_relacional(cliente_id: int, produto_id: int, quantidade: int) -> None:
    carrinho_id = _garantir_carrinho_relacional(cliente_id)
    existente = db.executar_leitura_um(
        "SELECT id, quantidade FROM itens_carrinho WHERE carrinho_id = %s AND produto_id = %s",
        (carrinho_id, produto_id),
    )
    if existente:
        nova_qtd = existente["quantidade"] + quantidade
        db.executar_escrita(
            "UPDATE itens_carrinho SET quantidade = %s WHERE id = %s",
            (nova_qtd, existente["id"]),
        )
    else:
        db.executar_escrita(
            "INSERT INTO itens_carrinho (carrinho_id, produto_id, quantidade) VALUES (%s, %s, %s)",
            (carrinho_id, produto_id, quantidade),
        )


def _get_cart_relacional(cliente_id: int) -> list:
    return db.executar_leitura(
        """
        SELECT ic.produto_id,
               p.nome        AS nome_produto,
               p.preco       AS preco,
               p.imagem      AS imagem,
               ic.quantidade AS quantidade
        FROM carrinho c
        JOIN itens_carrinho ic ON ic.carrinho_id = c.id
        JOIN produtos p        ON p.id = ic.produto_id
        WHERE c.cliente_id = %s
        ORDER BY p.nome
        """,
        (cliente_id,),
    )


def _remove_item_relacional(cliente_id: int, produto_id: int) -> None:
    carrinho = db.executar_leitura_um(
        "SELECT id FROM carrinho WHERE cliente_id = %s ORDER BY id DESC LIMIT 1",
        (cliente_id,),
    )
    if not carrinho:
        return
    db.executar_escrita(
        "DELETE FROM itens_carrinho WHERE carrinho_id = %s AND produto_id = %s",
        (carrinho["id"], produto_id),
    )


def _clear_cart_relacional(cliente_id: int) -> None:
    carrinho = db.executar_leitura_um(
        "SELECT id FROM carrinho WHERE cliente_id = %s ORDER BY id DESC LIMIT 1",
        (cliente_id,),
    )
    if not carrinho:
        return
    db.executar_escrita(
        "DELETE FROM itens_carrinho WHERE carrinho_id = %s",
        (carrinho["id"],),
    )


# ---------------------------------------------------------------------------
# Backend DYNAMODB (Projeto 03 — 03-dynamodb-recovery)
# ---------------------------------------------------------------------------
#
# Modelo da tabela `carrinho-lab`:
#   - PK  cliente_id     (String)  -> chave de partição
#   - SK  produto_id     (String)  -> chave de ordenação
#   - quantidade         (Number)
#   - nome_produto       (String)  -> desnormalizado a partir do relacional
#   - preco              (Number)  -> desnormalizado a partir do relacional
#   - atualizado_em      (String)  -> data/hora ISO-8601 (UTC)
#
# Observações de design:
#   - O recurso boto3 é criado de forma PREGUIÇOSA (lazy) em `_tabela()`. Assim
#     a simples importação de `cart.py` NÃO exige credenciais AWS — importante
#     para o modo relacional e para os testes locais.
#   - `cliente_id` e `produto_id` são gravados como String no DynamoDB, então
#     convertemos os ids recebidos (int no relacional) para str.
#   - Os campos numéricos voltam do DynamoDB como `Decimal`; convertemos para
#     int/float antes de devolver aos templates (que fazem `preco * quantidade`
#     e formatação `%.2f`).
#   - O atributo `imagem` NÃO é usado pelo template do carrinho
#     (`templates/carrinho.html` exibe apenas nome_produto, quantidade, preco e
#     subtotal). Por isso ele não é desnormalizado no item DynamoDB; se um dia
#     for necessário, pode ser buscado no relacional em `get_cart`.

# Cache preguiçoso do recurso Table do DynamoDB (memoização simples).
_tabela_cache = None


def _tabela():
    """
    Devolve (e memoiza) o recurso `Table` do DynamoDB do carrinho.

    A criação é preguiçosa: só ocorre no primeiro uso de um método DynamoDB,
    evitando exigir credenciais/boto3 apenas por importar o módulo. Usa a
    região de `Config.AWS_REGION` e o nome de `Config.DYNAMODB_TABLE`.
    """
    global _tabela_cache
    if _tabela_cache is None:
        import boto3  # import local para não exigir boto3 no modo relacional

        recurso = boto3.resource("dynamodb", region_name=Config.AWS_REGION)
        _tabela_cache = recurso.Table(Config.DYNAMODB_TABLE)
    return _tabela_cache


def _agora_iso() -> str:
    """Retorna o instante atual em UTC no formato ISO-8601 (para `atualizado_em`)."""
    return datetime.now(timezone.utc).isoformat()


def _para_numero(valor):
    """
    Converte um valor vindo do DynamoDB (tipicamente `Decimal`) em int ou float,
    para uso nos templates. Inteiros exatos viram `int`; caso contrário `float`.
    """
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    if valor is None:
        return 0
    return valor


def _buscar_produto_relacional(produto_id: int) -> dict:
    """
    Busca nome e preço do produto no banco relacional para desnormalizar no item
    do carrinho DynamoDB. Retorna dict com `nome`/`preco` ou valores padrão.
    """
    produto = db.executar_leitura_um(
        "SELECT nome, preco FROM produtos WHERE id = %s", (produto_id,)
    )
    if not produto:
        logger.warning("Produto id=%s nao encontrado no relacional ao adicionar ao carrinho", produto_id)
        return {"nome": f"Produto {produto_id}", "preco": Decimal("0")}
    # DynamoDB exige Decimal para tipos Number; convertemos o preco relacional.
    return {"nome": produto["nome"], "preco": Decimal(str(produto["preco"]))}


def _add_item_dynamodb(cliente_id: int, produto_id: int, quantidade: int) -> None:
    """
    Adiciona (ou incrementa) um item no carrinho DynamoDB.

    Se o item (cliente_id+produto_id) já existir, incrementa `quantidade` via
    UpdateItem (ADD). Sempre atualiza `nome_produto`/`preco` (desnormalizados do
    relacional) e `atualizado_em`.
    """
    produto = _buscar_produto_relacional(produto_id)
    _tabela().update_item(
        Key={"cliente_id": str(cliente_id), "produto_id": str(produto_id)},
        UpdateExpression=(
            "ADD quantidade :q "
            "SET nome_produto = :n, preco = :p, atualizado_em = :t"
        ),
        ExpressionAttributeValues={
            ":q": Decimal(int(quantidade)),
            ":n": produto["nome"],
            ":p": produto["preco"],
            ":t": _agora_iso(),
        },
    )


def _get_cart_dynamodb(cliente_id: int) -> list:
    """
    Lê os itens do carrinho do cliente via Query pela PK `cliente_id`.

    Devolve dicts com as MESMAS chaves esperadas pelos templates/rotas:
    `produto_id`, `nome_produto`, `preco` (float), `quantidade` (int).
    """
    from boto3.dynamodb.conditions import Key

    resposta = _tabela().query(
        KeyConditionExpression=Key("cliente_id").eq(str(cliente_id))
    )
    itens = []
    for item in resposta.get("Items", []):
        itens.append(
            {
                # produto_id volta como String; convertemos para int para casar
                # com o restante da aplicação (relacional usa ids inteiros).
                "produto_id": int(item["produto_id"]),
                "nome_produto": item.get("nome_produto", ""),
                "preco": _para_numero(item.get("preco")),
                "quantidade": _para_numero(item.get("quantidade")),
            }
        )
    # Ordena por nome para exibição estável (equivalente ao ORDER BY relacional).
    itens.sort(key=lambda i: i["nome_produto"])
    return itens


def _remove_item_dynamodb(cliente_id: int, produto_id: int) -> None:
    """Remove um item específico do carrinho (DeleteItem pela chave composta)."""
    _tabela().delete_item(
        Key={"cliente_id": str(cliente_id), "produto_id": str(produto_id)}
    )


def _clear_cart_dynamodb(cliente_id: int) -> None:
    """
    Esvazia o carrinho do cliente: consulta os itens da partição e apaga todos
    usando um `batch_writer` (eficiente para múltiplas exclusões).
    """
    from boto3.dynamodb.conditions import Key

    tabela = _tabela()
    resposta = tabela.query(
        KeyConditionExpression=Key("cliente_id").eq(str(cliente_id)),
        ProjectionExpression="cliente_id, produto_id",
    )
    itens = resposta.get("Items", [])
    if not itens:
        return
    with tabela.batch_writer() as lote:
        for item in itens:
            lote.delete_item(
                Key={
                    "cliente_id": item["cliente_id"],
                    "produto_id": item["produto_id"],
                }
            )


# ---------------------------------------------------------------------------
# Interface pública (roteia para o backend conforme CART_MODE)
# ---------------------------------------------------------------------------
def add_item(cliente_id: int, produto_id: int, quantidade: int = 1) -> None:
    """Adiciona (ou incrementa) um item no carrinho do cliente."""
    if quantidade <= 0:
        quantidade = 1
    logger.info("add_item cliente=%s produto=%s qtd=%s modo=%s",
                cliente_id, produto_id, quantidade, Config.CART_MODE)
    if Config.CART_MODE == "dynamodb":
        return _add_item_dynamodb(cliente_id, produto_id, quantidade)
    return _add_item_relacional(cliente_id, produto_id, quantidade)


def get_cart(cliente_id: int) -> list:
    """Devolve os itens do carrinho do cliente (lista de dicionários)."""
    if Config.CART_MODE == "dynamodb":
        return _get_cart_dynamodb(cliente_id)
    return _get_cart_relacional(cliente_id)


def remove_item(cliente_id: int, produto_id: int) -> None:
    """Remove um item específico do carrinho do cliente."""
    logger.info("remove_item cliente=%s produto=%s modo=%s",
                cliente_id, produto_id, Config.CART_MODE)
    if Config.CART_MODE == "dynamodb":
        return _remove_item_dynamodb(cliente_id, produto_id)
    return _remove_item_relacional(cliente_id, produto_id)


def clear_cart(cliente_id: int) -> None:
    """Esvazia o carrinho do cliente."""
    logger.info("clear_cart cliente=%s modo=%s", cliente_id, Config.CART_MODE)
    if Config.CART_MODE == "dynamodb":
        return _clear_cart_dynamodb(cliente_id)
    return _clear_cart_relacional(cliente_id)
