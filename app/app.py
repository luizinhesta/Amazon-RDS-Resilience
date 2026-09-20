"""
app.py — Ponto de entrada Flask da AWS Database Lab Store.

Rotas implementadas (Requisitos 1 e 2):
- /              -> página inicial com a lista de produtos
- /produtos      -> listar / cadastrar / editar produtos
- /clientes      -> listar / cadastrar clientes
- /pedidos       -> listar / criar pedidos
- /carrinho      -> carrinho simples (backend relacional na Fase 0)
- /database-lab  -> painel do laboratório (projeto, versão, banco, recursos,
                    objetivo e status de conectividade via SELECT 1)

Observações de arquitetura:
- INSERT/UPDATE/DELETE usam a conexão de ESCRITA (writer).
- SELECT das páginas de leitura usam a conexão de LEITURA (reader se houver).
- Nenhuma ação administrativa perigosa (failover/backup/restore) é exposta na UI
  (Requisito 1.8) — isso é feito manualmente pelo Console AWS.
"""

import logging

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

import cart
import db
import storage
from config import Config

# ---------------------------------------------------------------------------
# Configuração de logging (registra endpoint WRITER/READER, erros, modos)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")

app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY

# Cliente padrão usado pelo carrinho na Fase 0 (sem autenticação/sessão real).
# Mantém o laboratório simples: o foco é o banco, não o gerenciamento de sessão.
CLIENTE_PADRAO_CARRINHO = 1


# ---------------------------------------------------------------------------
# Helpers de exibição
# ---------------------------------------------------------------------------
@app.context_processor
def injetar_helpers():
    """Disponibiliza funções auxiliares para todos os templates."""
    def imagem_url(referencia):
        url = storage.url_imagem(referencia)
        if storage.eh_url_absoluta(referencia):
            return url
        # No modo local, resolve via /static.
        return url_for("static", filename=url)

    return {
        "imagem_url": imagem_url,
        "lab_project": Config.LAB_PROJECT,
        "lab_arch_version": Config.LAB_ARCH_VERSION,
    }


# ---------------------------------------------------------------------------
# Página inicial
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Página inicial: exibe a lista de produtos (Requisito 1.1)."""
    produtos = db.executar_leitura(
        "SELECT id, nome, descricao, preco, estoque, imagem FROM produtos ORDER BY nome"
    )
    return render_template("index.html", produtos=produtos)


# ---------------------------------------------------------------------------
# Produtos: listar, cadastrar, editar
# ---------------------------------------------------------------------------
@app.route("/produtos")
def produtos():
    """Lista os produtos e prepara o formulário de cadastro/edição."""
    lista = db.executar_leitura(
        "SELECT id, nome, descricao, preco, estoque, imagem FROM produtos ORDER BY nome"
    )
    # Se veio ?editar=<id>, carrega o produto para o formulário.
    editar_id = request.args.get("editar", type=int)
    produto_edicao = None
    if editar_id:
        produto_edicao = db.executar_leitura_um(
            "SELECT id, nome, descricao, preco, estoque, imagem FROM produtos WHERE id = %s",
            (editar_id,),
        )
    return render_template("produtos.html", produtos=lista, produto_edicao=produto_edicao)


@app.route("/produtos/salvar", methods=["POST"])
def salvar_produto():
    """Cadastra um novo produto ou atualiza um existente."""
    produto_id = request.form.get("id", type=int)
    nome = (request.form.get("nome") or "").strip()
    descricao = (request.form.get("descricao") or "").strip()
    preco = request.form.get("preco", type=float) or 0.0
    estoque = request.form.get("estoque", type=int) or 0
    imagem = (request.form.get("imagem") or "").strip()

    if not nome:
        flash("O nome do produto é obrigatório.", "erro")
        return redirect(url_for("produtos"))

    if produto_id:
        db.executar_escrita(
            """
            UPDATE produtos
               SET nome = %s, descricao = %s, preco = %s, estoque = %s, imagem = %s
             WHERE id = %s
            """,
            (nome, descricao, preco, estoque, imagem, produto_id),
        )
        flash(f"Produto '{nome}' atualizado com sucesso.", "sucesso")
    else:
        db.executar_escrita(
            "INSERT INTO produtos (nome, descricao, preco, estoque, imagem) VALUES (%s, %s, %s, %s, %s)",
            (nome, descricao, preco, estoque, imagem),
        )
        flash(f"Produto '{nome}' cadastrado com sucesso.", "sucesso")

    return redirect(url_for("produtos"))


# ---------------------------------------------------------------------------
# Clientes: listar, cadastrar
# ---------------------------------------------------------------------------
@app.route("/clientes")
def clientes():
    """Lista os clientes cadastrados."""
    lista = db.executar_leitura(
        "SELECT id, nome, email, telefone, criado_em FROM clientes ORDER BY nome"
    )
    return render_template("clientes.html", clientes=lista)


@app.route("/clientes/salvar", methods=["POST"])
def salvar_cliente():
    """Cadastra um novo cliente."""
    nome = (request.form.get("nome") or "").strip()
    email = (request.form.get("email") or "").strip()
    telefone = (request.form.get("telefone") or "").strip()

    if not nome or not email:
        flash("Nome e e-mail são obrigatórios.", "erro")
        return redirect(url_for("clientes"))

    try:
        db.executar_escrita(
            "INSERT INTO clientes (nome, email, telefone) VALUES (%s, %s, %s)",
            (nome, email, telefone),
        )
        flash(f"Cliente '{nome}' cadastrado com sucesso.", "sucesso")
    except Exception as exc:  # noqa: BLE001 — ex.: e-mail duplicado (UNIQUE)
        logger.warning("Falha ao cadastrar cliente: %s", exc)
        flash("Não foi possível cadastrar o cliente (e-mail já existe?).", "erro")

    return redirect(url_for("clientes"))


# ---------------------------------------------------------------------------
# Pedidos: listar, criar, consultar
# ---------------------------------------------------------------------------
@app.route("/pedidos")
def pedidos():
    """Lista pedidos e prepara dados para o formulário de criação."""
    lista = db.executar_leitura(
        """
        SELECT p.id, p.status, p.total, p.criado_em, c.nome AS cliente_nome
        FROM pedidos p
        JOIN clientes c ON c.id = p.cliente_id
        ORDER BY p.id DESC
        """
    )
    lista_clientes = db.executar_leitura("SELECT id, nome FROM clientes ORDER BY nome")
    lista_produtos = db.executar_leitura(
        "SELECT id, nome, preco FROM produtos ORDER BY nome"
    )

    # Se veio ?detalhe=<id>, carrega os itens do pedido.
    detalhe_id = request.args.get("detalhe", type=int)
    itens = []
    pedido_detalhe = None
    if detalhe_id:
        pedido_detalhe = db.executar_leitura_um(
            """
            SELECT p.id, p.status, p.total, p.criado_em, c.nome AS cliente_nome
            FROM pedidos p
            JOIN clientes c ON c.id = p.cliente_id
            WHERE p.id = %s
            """,
            (detalhe_id,),
        )
        itens = db.executar_leitura(
            """
            SELECT ip.produto_id, pr.nome AS nome_produto,
                   ip.quantidade, ip.preco_unitario
            FROM itens_pedido ip
            JOIN produtos pr ON pr.id = ip.produto_id
            WHERE ip.pedido_id = %s
            """,
            (detalhe_id,),
        )

    return render_template(
        "pedidos.html",
        pedidos=lista,
        clientes=lista_clientes,
        produtos=lista_produtos,
        pedido_detalhe=pedido_detalhe,
        itens=itens,
    )


@app.route("/pedidos/criar", methods=["POST"])
def criar_pedido():
    """
    Cria um pedido com um único produto (fluxo simples da Fase 0).

    Calcula o total, grava o pedido e o item, tudo pela conexão de escrita.
    """
    cliente_id = request.form.get("cliente_id", type=int)
    produto_id = request.form.get("produto_id", type=int)
    quantidade = request.form.get("quantidade", type=int) or 1

    if not cliente_id or not produto_id:
        flash("Selecione cliente e produto para criar o pedido.", "erro")
        return redirect(url_for("pedidos"))

    produto = db.executar_leitura_um(
        "SELECT id, preco FROM produtos WHERE id = %s", (produto_id,)
    )
    if not produto:
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("pedidos"))

    preco_unitario = float(produto["preco"])
    total = preco_unitario * max(quantidade, 1)

    pedido_id = db.executar_escrita(
        "INSERT INTO pedidos (cliente_id, status, total) VALUES (%s, %s, %s)",
        (cliente_id, "CRIADO", total),
    )
    db.executar_escrita(
        """
        INSERT INTO itens_pedido (pedido_id, produto_id, quantidade, preco_unitario)
        VALUES (%s, %s, %s, %s)
        """,
        (pedido_id, produto_id, quantidade, preco_unitario),
    )

    flash(f"Pedido #{pedido_id} criado com sucesso.", "sucesso")
    return redirect(url_for("pedidos", detalhe=pedido_id))


# ---------------------------------------------------------------------------
# Carrinho (backend relacional na Fase 0)
# ---------------------------------------------------------------------------
@app.route("/carrinho")
def carrinho():
    """Exibe o carrinho do cliente padrão."""
    itens = cart.get_cart(CLIENTE_PADRAO_CARRINHO)
    lista_produtos = db.executar_leitura(
        "SELECT id, nome, preco FROM produtos ORDER BY nome"
    )
    total = sum(float(i["preco"]) * i["quantidade"] for i in itens)
    return render_template(
        "carrinho.html",
        itens=itens,
        produtos=lista_produtos,
        total=total,
    )


@app.route("/carrinho/adicionar", methods=["POST"])
def carrinho_adicionar():
    """Adiciona um produto ao carrinho."""
    produto_id = request.form.get("produto_id", type=int)
    quantidade = request.form.get("quantidade", type=int) or 1
    if produto_id:
        cart.add_item(CLIENTE_PADRAO_CARRINHO, produto_id, quantidade)
        flash("Produto adicionado ao carrinho.", "sucesso")
    return redirect(url_for("carrinho"))


@app.route("/carrinho/remover", methods=["POST"])
def carrinho_remover():
    """Remove um produto do carrinho."""
    produto_id = request.form.get("produto_id", type=int)
    if produto_id:
        cart.remove_item(CLIENTE_PADRAO_CARRINHO, produto_id)
        flash("Produto removido do carrinho.", "sucesso")
    return redirect(url_for("carrinho"))


@app.route("/carrinho/limpar", methods=["POST"])
def carrinho_limpar():
    """Esvazia o carrinho."""
    cart.clear_cart(CLIENTE_PADRAO_CARRINHO)
    flash("Carrinho esvaziado.", "sucesso")
    return redirect(url_for("carrinho"))


# ---------------------------------------------------------------------------
# Painel do laboratório
# ---------------------------------------------------------------------------
@app.route("/database-lab")
def database_lab():
    """
    Painel informativo do laboratório (Requisito 1.7).

    Exibe projeto, versão da arquitetura, banco utilizado, recursos, objetivo
    da fase e status de conectividade (SELECT 1 no writer e, se houver, reader).
    Nenhuma ação administrativa perigosa é exposta (Requisito 1.8).
    """
    conectividade = [db.testar_conectividade(usar_reader=False)]
    if Config.tem_reader_dedicado():
        conectividade.append(db.testar_conectividade(usar_reader=True))

    contexto = {
        "projeto": Config.LAB_PROJECT,
        "versao_arquitetura": Config.LAB_ARCH_VERSION,
        "banco": Config.descrever_banco(),
        "recursos": Config.resumo_recursos(),
        "objetivo": _descrever_objetivo(),
        "conectividade": conectividade,
        "storage": storage.status_storage(),
        "cart_mode": Config.CART_MODE,
    }
    return render_template("database-lab.html", **contexto)


def _descrever_objetivo() -> str:
    """
    Objetivo da fase exibido em /database-lab.

    O texto acompanha a arquitetura em uso (deduzida dinamicamente do endpoint
    do banco e do modo de armazenamento), de modo que o painel reflita a fase
    atual sem depender de texto fixo:

    - Fase 0 (MySQL local): reforça a linha de base com SPOF.
    - Fase 1+ (RDS/Aurora) com imagens locais: reforça o desacoplamento —
      compute separado de database.
    - Fase 4 (RDS/Aurora + imagens no S3): descreve a arquitetura final do
      Projeto 01, em que também os arquivos deixam de depender da EC2.
    """
    if Config.banco_e_local():
        return (
            "Provar que a aplicação monolítica funciona em uma única EC2 "
            "(aplicação + MySQL + banco + imagens locais), estabelecendo a "
            "linha de base com SPOF antes de qualquer melhoria."
        )
    if Config.STORAGE_MODE == "s3":
        # Arquitetura final do Projeto 01: banco gerenciado + imagens no S3.
        return (
            "Arquitetura final do Projeto 01: o banco roda em serviço gerenciado "
            f"({Config.tipo_banco()}) e as imagens são servidas do Amazon S3. "
            "Compute (EC2), banco (RDS) e arquivos (S3) estão desacoplados — a EC2 "
            "pode falhar, ser reiniciada ou substituída sem levar dados nem imagens "
            "junto. Recursos de alta disponibilidade (Multi-AZ) e de escala de "
            "leitura (Read Replica) foram comprovados nas Fases 2 e 3 e podem ser "
            "reativados sob demanda."
        )
    return (
        "Separar o banco de dados da EC2 usando um serviço gerenciado "
        f"({Config.tipo_banco()}): a aplicação continua na EC2 e o banco passa "
        "a ser independente da instância — compute separado de database. "
        "A EC2 pode falhar, ser reiniciada ou substituída sem levar os dados junto."
    )


if __name__ == "__main__":
    # Em produção (EC2) recomenda-se um WSGI server; para o laboratório o
    # servidor de desenvolvimento do Flask é suficiente.
    app.run(host="0.0.0.0", port=5000, debug=(Config.FLASK_ENV == "development"))
