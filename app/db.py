"""
db.py — Camada de acesso ao banco relacional (MySQL / RDS / Aurora).

Conceitos-chave do laboratório:
- get_write_connection(): sempre conecta no DB_WRITER_ENDPOINT.
- get_read_connection(): conecta no DB_READER_ENDPOINT se ele existir; caso
  contrário, usa o writer (comportamento seguro por padrão).
- Cada abertura de conexão registra em log QUAL endpoint foi usado
  (WRITER ou READER). Esse log é essencial para comprovar a Fase 3
  (Read Replica = escalabilidade de leitura).

Regra de ouro (Requisito 5):
- INSERT/UPDATE/DELETE sempre pela conexão de ESCRITA.
- SELECT de páginas de leitura PODE usar a conexão de LEITURA.
"""

import logging

import pymysql
from pymysql.cursors import DictCursor

from config import Config

# Logger dedicado à camada de banco. A aplicação configura o handler/format.
logger = logging.getLogger("db")


def _abrir_conexao(host: str, papel: str):
    """
    Abre uma conexão PyMySQL com o host informado e registra em log o papel
    (WRITER/READER) e o endpoint utilizado.

    :param host: endpoint do banco (writer ou reader)
    :param papel: "WRITER" ou "READER" — apenas para fins de log/evidência
    """
    logger.info("Conexao de banco [%s] -> endpoint=%s:%s db=%s",
                papel, host, Config.DB_PORT, Config.DB_NAME)
    return pymysql.connect(
        host=host,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def get_write_connection():
    """Retorna uma conexão para o endpoint de ESCRITA (writer)."""
    return _abrir_conexao(Config.DB_WRITER_ENDPOINT, "WRITER")


def get_read_connection():
    """
    Retorna uma conexão para o endpoint de LEITURA (reader).

    Se não houver um reader dedicado (DB_READER_ENDPOINT vazio), usa o writer.
    """
    if Config.tem_reader_dedicado():
        return _abrir_conexao(Config.DB_READER_ENDPOINT, "READER")
    # Sem reader dedicado: leitura cai no writer (padrão seguro).
    return _abrir_conexao(Config.DB_WRITER_ENDPOINT, "READER(via WRITER)")


def executar_leitura(sql: str, parametros=None):
    """
    Executa um SELECT usando a conexão de LEITURA e devolve todas as linhas.

    :return: lista de dicionários (uma entrada por linha)
    """
    conexao = get_read_connection()
    try:
        with conexao.cursor() as cursor:
            cursor.execute(sql, parametros or ())
            return cursor.fetchall()
    finally:
        conexao.close()


def executar_leitura_um(sql: str, parametros=None):
    """Executa um SELECT de leitura e devolve apenas a primeira linha (ou None)."""
    conexao = get_read_connection()
    try:
        with conexao.cursor() as cursor:
            cursor.execute(sql, parametros or ())
            return cursor.fetchone()
    finally:
        conexao.close()


def executar_escrita(sql: str, parametros=None):
    """
    Executa um INSERT/UPDATE/DELETE usando a conexão de ESCRITA (writer).

    Faz commit ao final e retorna o id gerado (lastrowid), útil em INSERTs.
    """
    conexao = get_write_connection()
    try:
        with conexao.cursor() as cursor:
            cursor.execute(sql, parametros or ())
            id_gerado = cursor.lastrowid
        conexao.commit()
        return id_gerado
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def testar_conectividade(usar_reader: bool = False) -> dict:
    """
    Executa um `SELECT 1` para comprovar a conectividade (usado em /database-lab).

    :param usar_reader: quando True testa o reader; caso contrário, o writer.
    :return: dicionário com status ("OK"/"ERRO"), endpoint e mensagem de erro.
    """
    if usar_reader:
        endpoint = Config.DB_READER_ENDPOINT or Config.DB_WRITER_ENDPOINT
        abrir = get_read_connection
        papel = "READER"
    else:
        endpoint = Config.DB_WRITER_ENDPOINT
        abrir = get_write_connection
        papel = "WRITER"

    try:
        conexao = abrir()
        try:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        finally:
            conexao.close()
        return {"papel": papel, "endpoint": endpoint, "status": "OK", "erro": None}
    except Exception as exc:  # noqa: BLE001 — queremos capturar qualquer falha de conexão
        logger.warning("Falha de conectividade [%s] em %s: %s", papel, endpoint, exc)
        return {"papel": papel, "endpoint": endpoint, "status": "ERRO", "erro": str(exc)}
