"""
config.py — Leitura de configuração a partir de variáveis de ambiente.

Princípio de segurança (Requisito 11): nenhuma credencial fica no código.
Todos os valores sensíveis (host, usuário, senha) vêm de variáveis de ambiente,
normalmente carregadas de um arquivo `.env` (que fica fora do Git).

Este módulo apenas lê o ambiente e expõe uma classe `Config` com os valores
já normalizados. Nenhuma senha padrão é embutida aqui.
"""

import os


def _get_bool(nome: str, padrao: bool = False) -> bool:
    """Converte uma variável de ambiente em booleano de forma tolerante."""
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "yes", "sim", "on")


def _tentar_carregar_dotenv() -> None:
    """
    Carrega variáveis de um arquivo `.env` quando a biblioteca python-dotenv
    estiver disponível. É opcional: em produção as variáveis normalmente já
    estão no ambiente do sistema/serviço.
    """
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        # python-dotenv é opcional; se não estiver instalado, seguimos com
        # as variáveis já presentes no ambiente do sistema operacional.
        pass


_tentar_carregar_dotenv()


class Config:
    """
    Configuração da aplicação AWS Database Lab Store.

    Os nomes das variáveis seguem o design do laboratório. Cada fase do projeto
    passa a usar variáveis adicionais (ver tabela no design.md).
    """

    # ----- Flask -----
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-lab")

    # ----- Banco relacional (MySQL / RDS / Aurora) -----
    # Endpoint de ESCRITA (writer). Na Fase 0 é o MySQL local ("localhost").
    DB_WRITER_ENDPOINT = os.getenv("DB_WRITER_ENDPOINT", "localhost")
    # Endpoint de LEITURA (reader). Opcional: só existe a partir da Fase 3
    # (Read Replica) ou no Aurora Reader. Se vazio, a leitura usa o writer.
    DB_READER_ENDPOINT = os.getenv("DB_READER_ENDPOINT") or None
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "loja")
    DB_USER = os.getenv("DB_USER", "app_loja")
    # Sem senha padrão embutida: vem exclusivamente do ambiente.
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # ----- Armazenamento de imagens -----
    # "local" (Fase 0..3) ou "s3" (Fase 4).
    STORAGE_MODE = os.getenv("STORAGE_MODE", "local").strip().lower()
    S3_BUCKET = os.getenv("S3_BUCKET", "")
    S3_REGION = os.getenv("S3_REGION", "")

    # ----- Carrinho -----
    # "relational" (Fase 0..Projeto 02) ou "dynamodb" (Projeto 03+).
    CART_MODE = os.getenv("CART_MODE", "relational").strip().lower()
    DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "carrinho-lab")

    # ----- AWS -----
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # ----- Rótulos exibidos em /database-lab -----
    LAB_PROJECT = os.getenv("LAB_PROJECT", "Projeto 01 — AWS RDS Resilience Lab")
    LAB_ARCH_VERSION = os.getenv("LAB_ARCH_VERSION", "Fase 0 — Monolito em EC2")

    @classmethod
    def tem_reader_dedicado(cls) -> bool:
        """Indica se há um endpoint de leitura separado do writer."""
        return bool(cls.DB_READER_ENDPOINT)

    @classmethod
    def banco_e_local(cls) -> bool:
        """Indica se o banco de escrita é o MySQL local da própria EC2 (Fase 0)."""
        return cls.DB_WRITER_ENDPOINT in ("localhost", "127.0.0.1")

    @staticmethod
    def _host_e_aurora(host: str) -> bool:
        """
        Indica se um hostname de endpoint gerenciado AWS pertence a um cluster
        Aurora. Os endpoints do Aurora trazem sempre o token `cluster-` no
        hostname, em duas variações:

        - **Cluster Endpoint** (writer): `nome.cluster-xxxx.<regiao>.rds.amazonaws.com`
        - **Reader Endpoint**  (leitor): `nome.cluster-ro-xxxx.<regiao>.rds.amazonaws.com`

        Também há endpoints personalizados do Aurora com `cluster-custom-...`.
        Todos contêm a subcadeia `cluster-`, então essa verificação cobre o
        Cluster Endpoint, o Reader Endpoint (`.cluster-ro-`) e endpoints custom.
        """
        h = (host or "").lower()
        if not h:
            return False
        # Restringe a endpoints gerenciados AWS (rds.amazonaws.com) e exige o
        # token "cluster-" (cobre cluster, cluster-ro e cluster-custom).
        e_gerenciado = ".rds." in h or h.endswith(".rds.amazonaws.com")
        return e_gerenciado and "cluster-" in h

    @classmethod
    def tipo_banco(cls) -> str:
        """
        Deduz o tipo/serviço do banco a partir dos endpoints configurados.

        A dedução é feita pelo padrão do hostname do endpoint gerenciado AWS,
        de forma que o rótulo em /database-lab reflita **dinamicamente** a fase
        atual sem precisar de texto fixo:

        - `localhost`/`127.0.0.1`     -> "MySQL local" (Fase 0, monolito).
        - endpoint contendo `.rds.`   -> Amazon RDS ou Aurora:
            - writer OU reader com `cluster-` no host -> Aurora (Cluster/Reader
              Endpoint, incluindo o `.cluster-ro-` do leitor) — Projeto 02.
            - caso contrário                          -> RDS MySQL — Projeto 01.
        - qualquer outro host          -> "Banco gerenciado" (fallback genérico).

        Observação: a verificação considera **tanto o writer quanto o reader**.
        Assim, mesmo que apenas o Reader Endpoint do Aurora (`.cluster-ro-`)
        esteja preenchido, ou que o writer use um endpoint de instância, o
        rótulo ainda reconhece corretamente o Aurora.

        Retorna um dos rótulos: "MySQL local", "RDS MySQL", "Aurora MySQL"
        ou "Banco gerenciado".
        """
        if cls.banco_e_local():
            return "MySQL local"
        writer = (cls.DB_WRITER_ENDPOINT or "").lower()
        reader = (cls.DB_READER_ENDPOINT or "").lower()
        # Aurora se qualquer um dos endpoints (writer/reader) for de cluster.
        if cls._host_e_aurora(writer) or cls._host_e_aurora(reader):
            return "Aurora MySQL"
        if ".rds." in writer or writer.endswith(".rds.amazonaws.com"):
            return "RDS MySQL"
        return "Banco gerenciado"

    @classmethod
    def descrever_banco(cls) -> str:
        """
        Descrição amigável do banco em uso, exibida em "Banco utilizado" no
        painel /database-lab. Combina o tipo deduzido (tipo_banco) com o
        endpoint/porta/nome e, quando houver reader dedicado, a topologia.

        Exemplos:
        - "MySQL local (localhost:3306/loja)"
        - "RDS MySQL — Single-AZ (rds-mysql-lab...:3306/loja)"
        - "RDS MySQL — Writer + Read Replica (writer .../reader ...)"
        - "Aurora MySQL — Cluster + Reader (...)"
        """
        tipo = cls.tipo_banco()
        writer = cls.DB_WRITER_ENDPOINT
        alvo = f"{writer}:{cls.DB_PORT}/{cls.DB_NAME}"

        if tipo == "MySQL local":
            return f"MySQL local ({alvo})"

        if tipo == "RDS MySQL":
            if cls.tem_reader_dedicado():
                # Fase 3: writer (primário) + Read Replica.
                return (
                    "RDS MySQL — Writer + Read Replica "
                    f"(writer {writer} / reader {cls.DB_READER_ENDPOINT})"
                )
            # Fase 1/2: instância única (Single-AZ ou Multi-AZ, mesmo endpoint).
            return f"RDS MySQL — Single-AZ ({alvo})"

        if tipo == "Aurora MySQL":
            if cls.tem_reader_dedicado():
                return (
                    "Aurora MySQL — Cluster + Reader "
                    f"(cluster {writer} / reader {cls.DB_READER_ENDPOINT})"
                )
            return f"Aurora MySQL — Cluster ({alvo})"

        # Fallback genérico para qualquer outro endpoint gerenciado.
        return f"Banco gerenciado ({alvo})"

    @classmethod
    def resumo_recursos(cls) -> str:
        """Descrição curta dos recursos em uso, exibida em /database-lab."""
        recursos = ["EC2 (aplicação Flask)"]
        if cls.banco_e_local():
            recursos.append("MySQL local (na própria EC2)")
        else:
            recursos.append(f"{cls.tipo_banco()} (writer: {cls.DB_WRITER_ENDPOINT})")
        if cls.tem_reader_dedicado():
            recursos.append(f"Read Replica / Reader ({cls.DB_READER_ENDPOINT})")
        if cls.STORAGE_MODE == "s3":
            recursos.append(f"Amazon S3 (bucket: {cls.S3_BUCKET})")
        else:
            recursos.append("Imagens locais (static/images)")
        if cls.CART_MODE == "dynamodb":
            recursos.append(f"DynamoDB (carrinho: {cls.DYNAMODB_TABLE})")
        else:
            recursos.append("Carrinho relacional (MySQL)")
        return " • ".join(recursos)
