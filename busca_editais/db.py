import sqlite3
from datetime import datetime

from .config import ARQUIVO_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS licitacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte TEXT NOT NULL,                -- 'pncp' | 'tcepi'
    id_fonte TEXT NOT NULL,             -- identificador único na fonte
    orgao TEXT,
    municipio TEXT,
    uf TEXT,
    modalidade TEXT,
    objeto TEXT,
    valor_estimado REAL,
    data_publicacao TEXT,
    data_abertura TEXT,
    data_encerramento TEXT,             -- fim do recebimento de propostas
    situacao TEXT,
    link TEXT,
    categoria TEXT,                     -- grupos casados, ex.: 'obras' ou 'climatizacao,obras'
    termos_casados TEXT,
    status TEXT NOT NULL DEFAULT 'novo',-- novo | visto | interesse | descartado
    notificado INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    UNIQUE (fonte, id_fonte)
);
CREATE INDEX IF NOT EXISTS idx_lic_status ON licitacoes (status);
CREATE INDEX IF NOT EXISTS idx_lic_encerramento ON licitacoes (data_encerramento);
"""


def conectar():
    con = sqlite3.connect(ARQUIVO_DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert(con, item):
    """Insere ou atualiza uma licitação. Preserva status/notificado se já existe.
    Retorna True se é registro novo."""
    agora = datetime.now().isoformat(timespec="seconds")
    existente = con.execute(
        "SELECT id FROM licitacoes WHERE fonte=? AND id_fonte=?",
        (item["fonte"], item["id_fonte"]),
    ).fetchone()
    if existente:
        con.execute(
            """UPDATE licitacoes SET orgao=?, municipio=?, uf=?, modalidade=?,
               objeto=?, valor_estimado=?, data_publicacao=?, data_abertura=?,
               data_encerramento=?, situacao=?, link=?, categoria=?,
               termos_casados=?, atualizado_em=? WHERE id=?""",
            (item.get("orgao"), item.get("municipio"), item.get("uf"),
             item.get("modalidade"), item.get("objeto"), item.get("valor_estimado"),
             item.get("data_publicacao"), item.get("data_abertura"),
             item.get("data_encerramento"), item.get("situacao"), item.get("link"),
             item.get("categoria"), item.get("termos_casados"), agora,
             existente["id"]),
        )
        return False
    con.execute(
        """INSERT INTO licitacoes (fonte, id_fonte, orgao, municipio, uf, modalidade,
           objeto, valor_estimado, data_publicacao, data_abertura, data_encerramento,
           situacao, link, categoria, termos_casados, criado_em, atualizado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (item["fonte"], item["id_fonte"], item.get("orgao"), item.get("municipio"),
         item.get("uf"), item.get("modalidade"), item.get("objeto"),
         item.get("valor_estimado"), item.get("data_publicacao"),
         item.get("data_abertura"), item.get("data_encerramento"),
         item.get("situacao"), item.get("link"), item.get("categoria"),
         item.get("termos_casados"), agora, agora),
    )
    return True
