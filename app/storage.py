"""
storage.py — Abstração de armazenamento de imagens dos produtos.

A coluna `produtos.imagem` guarda sempre uma REFERÊNCIA (nome do arquivo ou
chave no S3), NUNCA o binário da imagem (Requisito 6).

Modos:
- STORAGE_MODE=local (Fase 0..3): as imagens ficam em `static/images/` e a
  URL exibida aponta para essa pasta servida pelo Flask.
- STORAGE_MODE=s3 (Fase 4): a URL é montada apontando para o objeto no bucket
  S3; o banco continua guardando apenas a chave/nome.

A interface pública é `url_imagem(referencia)`, que devolve a URL correta
conforme o modo configurado — isso permite trocar o backend sem alterar as
rotas nem os templates.
"""

import logging

from config import Config

logger = logging.getLogger("storage")

# Imagem exibida quando o produto não tem referência cadastrada.
IMAGEM_PADRAO = "sem-imagem.svg"


def _url_local(referencia: str) -> str:
    """Monta a URL de uma imagem servida localmente pelo Flask (static/images)."""
    # Caminho relativo a /static — o template usa url_for('static', ...).
    return f"images/{referencia}"


def _url_s3(referencia: str) -> str:
    """
    Monta a URL pública/estática de um objeto no Amazon S3.

    Usa o padrão de URL virtual-hosted-style regional. Na Fase 4 o bucket e a
    região vêm de S3_BUCKET e S3_REGION.
    """
    bucket = Config.S3_BUCKET
    regiao = Config.S3_REGION
    if not bucket:
        logger.warning("STORAGE_MODE=s3 mas S3_BUCKET nao esta definido; usando referencia crua.")
        return referencia
    if regiao:
        return f"https://{bucket}.s3.{regiao}.amazonaws.com/{referencia}"
    return f"https://{bucket}.s3.amazonaws.com/{referencia}"


def url_imagem(referencia: str) -> str:
    """
    Devolve a URL da imagem a partir da referência guardada no banco.

    - Se a referência estiver vazia, usa a imagem padrão.
    - Se STORAGE_MODE=s3, monta a URL do S3.
    - Caso contrário (local), monta o caminho dentro de static/images.

    Observação: no modo local o retorno é um caminho relativo a /static,
    pensado para uso com url_for('static', filename=...). No modo S3 o retorno
    já é uma URL absoluta.
    """
    ref = (referencia or "").strip() or IMAGEM_PADRAO

    # Se já for uma URL absoluta, devolve como está.
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref

    if Config.STORAGE_MODE == "s3":
        return _url_s3(ref)
    return _url_local(ref)


def eh_url_absoluta(referencia: str) -> bool:
    """Indica se a URL resultante já é absoluta (S3/HTTP) ou relativa a /static."""
    ref = (referencia or "").strip()
    if ref.startswith("http://") or ref.startswith("https://"):
        return True
    return Config.STORAGE_MODE == "s3"


def status_storage() -> dict:
    """Resumo do storage para exibição em /database-lab."""
    if Config.STORAGE_MODE == "s3":
        return {
            "modo": "s3",
            "detalhe": f"bucket={Config.S3_BUCKET or '(nao definido)'} regiao={Config.S3_REGION or '(nao definida)'}",
        }
    return {"modo": "local", "detalhe": "static/images/"}
