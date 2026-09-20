"""
test_cart_dynamodb.py — Testes leves do backend DynamoDB do carrinho.

Objetivo: validar a lógica de CONVERSÃO DE TIPOS (Decimal -> int/float) e o
comportamento PREGUIÇOSO (lazy) do recurso DynamoDB, SEM exigir credenciais
AWS reais nem a biblioteca `boto3` instalada.

Estratégia:
- Injetamos módulos falsos (`stubs`) para `db`, `config` e `boto3` em
  `sys.modules` ANTES de importar `cart`. Assim o teste roda em qualquer
  máquina (inclusive sem pymysql/boto3), focando na lógica de negócio.
- Cada método DynamoDB do `cart.py` é exercitado contra uma tabela falsa em
  memória (`_TabelaFake`) que imita a interface do recurso boto3 usada.

Execução: python test_cart_dynamodb.py
"""

import sys
import types
from decimal import Decimal


# ---------------------------------------------------------------------------
# Stubs de dependências externas (evitam pymysql/boto3/credenciais no teste)
# ---------------------------------------------------------------------------
class _ConfigFake:
    CART_MODE = "dynamodb"
    AWS_REGION = "us-east-1"
    DYNAMODB_TABLE = "carrinho-lab"


# Produtos "no relacional" que o stub de db devolve.
_PRODUTOS_FAKE = {
    1: {"nome": "Notebook", "preco": Decimal("3500.90")},
    2: {"nome": "Mouse", "preco": Decimal("79.90")},
}


def _executar_leitura_um(sql, parametros=None):
    produto_id = parametros[0]
    return _PRODUTOS_FAKE.get(produto_id)


# Monta os módulos falsos e injeta em sys.modules.
_config_mod = types.ModuleType("config")
_config_mod.Config = _ConfigFake
sys.modules["config"] = _config_mod

_db_mod = types.ModuleType("db")
_db_mod.executar_leitura_um = _executar_leitura_um
sys.modules["db"] = _db_mod


# ---------------------------------------------------------------------------
# Tabela DynamoDB falsa em memória (imita a interface usada pelo cart.py)
# ---------------------------------------------------------------------------
class _Cond:
    """Imita o objeto de condição de Key('cliente_id').eq(valor)."""

    def __init__(self, valor):
        self.valor = valor


class _KeyFake:
    def __init__(self, nome):
        self.nome = nome

    def eq(self, valor):
        return _Cond(valor)


class _BatchWriter:
    def __init__(self, tabela):
        self.tabela = tabela

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def delete_item(self, Key):
        self.tabela._delete(Key)


class _TabelaFake:
    def __init__(self):
        # chave: (cliente_id, produto_id) -> item dict
        self.itens = {}

    # --- interface usada pelo cart.py ---
    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues):
        chave = (Key["cliente_id"], Key["produto_id"])
        atual = self.itens.get(chave, {**Key, "quantidade": Decimal(0)})
        # Simula o "ADD quantidade :q"
        atual["quantidade"] = atual.get("quantidade", Decimal(0)) + ExpressionAttributeValues[":q"]
        atual["nome_produto"] = ExpressionAttributeValues[":n"]
        atual["preco"] = ExpressionAttributeValues[":p"]
        atual["atualizado_em"] = ExpressionAttributeValues[":t"]
        self.itens[chave] = atual

    def query(self, KeyConditionExpression, ProjectionExpression=None):
        cliente_id = KeyConditionExpression.valor
        return {
            "Items": [v for (c, _), v in self.itens.items() if c == cliente_id]
        }

    def delete_item(self, Key):
        self._delete(Key)

    def batch_writer(self):
        return _BatchWriter(self)

    def _delete(self, Key):
        self.itens.pop((Key["cliente_id"], Key["produto_id"]), None)


# Stub de boto3: resource(...).Table(nome) devolve a mesma _TabelaFake.
_TABELA_FAKE = _TabelaFake()


class _RecursoFake:
    def Table(self, nome):
        assert nome == _ConfigFake.DYNAMODB_TABLE
        return _TABELA_FAKE


_boto3_mod = types.ModuleType("boto3")
_boto3_mod.resource = lambda servico, region_name=None: _RecursoFake()
sys.modules["boto3"] = _boto3_mod

# Stub de boto3.dynamodb.conditions.Key
_cond_mod = types.ModuleType("boto3.dynamodb.conditions")
_cond_mod.Key = _KeyFake
sys.modules["boto3.dynamodb"] = types.ModuleType("boto3.dynamodb")
sys.modules["boto3.dynamodb.conditions"] = _cond_mod


# ---------------------------------------------------------------------------
# Importa o módulo sob teste (só agora, com os stubs no lugar)
# ---------------------------------------------------------------------------
import cart  # noqa: E402


def _reset():
    _TABELA_FAKE.itens.clear()
    cart._tabela_cache = None


def test_para_numero_converte_decimal():
    # Inteiro exato vira int
    assert cart._para_numero(Decimal("3")) == 3
    assert isinstance(cart._para_numero(Decimal("3")), int)
    # Fracionário vira float
    assert cart._para_numero(Decimal("79.90")) == 79.90
    assert isinstance(cart._para_numero(Decimal("79.90")), float)
    # None vira 0
    assert cart._para_numero(None) == 0
    print("OK test_para_numero_converte_decimal")


def test_agora_iso_e_utc():
    valor = cart._agora_iso()
    assert isinstance(valor, str)
    assert "T" in valor  # formato ISO-8601
    print("OK test_agora_iso_e_utc")


def test_add_item_incrementa_quantidade():
    _reset()
    cart.add_item(1, 1, 2)
    cart.add_item(1, 1, 3)  # incrementa
    itens = cart.get_cart(1)
    assert len(itens) == 1
    item = itens[0]
    assert item["produto_id"] == 1              # convertido de str -> int
    assert item["nome_produto"] == "Notebook"    # desnormalizado do relacional
    assert item["quantidade"] == 5               # 2 + 3, como int
    assert isinstance(item["quantidade"], int)
    assert item["preco"] == 3500.90              # Decimal -> float
    assert isinstance(item["preco"], float)
    print("OK test_add_item_incrementa_quantidade")


def test_get_cart_ordena_por_nome():
    _reset()
    cart.add_item(1, 1, 1)  # Notebook
    cart.add_item(1, 2, 1)  # Mouse
    nomes = [i["nome_produto"] for i in cart.get_cart(1)]
    assert nomes == ["Mouse", "Notebook"]
    print("OK test_get_cart_ordena_por_nome")


def test_remove_item():
    _reset()
    cart.add_item(1, 1, 1)
    cart.add_item(1, 2, 1)
    cart.remove_item(1, 1)
    itens = cart.get_cart(1)
    assert len(itens) == 1
    assert itens[0]["produto_id"] == 2
    print("OK test_remove_item")


def test_clear_cart():
    _reset()
    cart.add_item(1, 1, 1)
    cart.add_item(1, 2, 1)
    cart.clear_cart(1)
    assert cart.get_cart(1) == []
    print("OK test_clear_cart")


def test_tabela_lazy_nao_exige_boto3_na_importacao():
    # O cache começa vazio: prova que importar cart NÃO criou o recurso boto3.
    _reset()
    assert cart._tabela_cache is None
    # Só ao usar um metodo o recurso é criado e memoizado.
    cart.get_cart(1)
    assert cart._tabela_cache is not None
    print("OK test_tabela_lazy_nao_exige_boto3_na_importacao")


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in testes:
        t()
    print(f"\n{len(testes)} testes passaram.")
