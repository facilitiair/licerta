"""Exporta o radar (banco novo, data/radar.db) para docs/dados.json —
o site estático do GitHub Pages instalado no celular."""
import json
import os
from datetime import datetime

from app.db import Licitacao, PerfilMatch, Sessao, criar_tabelas

RAIZ = os.path.dirname(os.path.abspath(__file__))


def gerar():
    criar_tabelas()
    s = Sessao()
    # licitações que casaram com algum perfil, com os nomes dos perfis
    perfis_por_lic = {}
    for m in s.query(PerfilMatch).all():
        perfis_por_lic.setdefault(m.licitacao_id, set()).add(m.perfil.nome)
    itens = []
    for lic in (s.query(Licitacao).filter(Licitacao.id.in_(perfis_por_lic))
                .order_by(Licitacao.data_encerramento_proposta)):
        itens.append({
            "fonte": lic.fonte or "pncp",
            "id_fonte": lic.numero_controle_pncp,
            "orgao": lic.orgao_nome,
            "municipio": lic.municipio_nome,
            "uf": lic.uf,
            "modalidade": lic.modalidade_nome,
            "objeto": lic.objeto,
            "valor_estimado": lic.valor_total_estimado,
            "data_encerramento": (lic.data_encerramento_proposta or "")[:16],
            "situacao": lic.situacao,
            "link": lic.link_pncp or lic.link_sistema_origem,
            "categoria": ",".join(sorted(perfis_por_lic[lic.id])),
        })
    s.close()
    saida = {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "itens": itens,
    }
    destino = os.path.join(RAIZ, "docs", "dados.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(itens)} licitações exportadas para o site")


if __name__ == "__main__":
    gerar()
