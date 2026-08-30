"""Exporta o banco do radar para docs/dados.json (site estático do GitHub Pages)."""
import json
import os
from datetime import datetime

from busca_editais import db as db_mod
from busca_editais.config import RAIZ

CAMPOS = ["fonte", "id_fonte", "orgao", "municipio", "uf", "modalidade", "objeto",
          "valor_estimado", "data_encerramento", "situacao", "link", "categoria"]


def gerar():
    con = db_mod.conectar()
    linhas = con.execute(
        "SELECT * FROM licitacoes ORDER BY data_encerramento").fetchall()
    con.close()
    itens = [{c: l[c] for c in CAMPOS} for l in linhas]
    saida = {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "itens": itens,
    }
    destino = os.path.join(RAIZ, "docs", "dados.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(itens)} licitações exportadas para {destino}")


if __name__ == "__main__":
    gerar()
