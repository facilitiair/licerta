"""Radar de Editais — coleta PNCP + Mural TCE-PI, classifica e notifica.

Uso:
    python radar.py              # coleta, classifica, grava e envia digest
    python radar.py --sem-email  # coleta sem enviar/gerar digest
"""
import sys
import traceback

from busca_editais import config as cfg_mod
from busca_editais import db as db_mod
from busca_editais.digest import enviar
from busca_editais.fontes import pncp, tcepi
from busca_editais.matcher import classificar, normalizar


def _passa_filtros(item, config):
    municipios = config.get("municipios") or []
    if municipios:
        alvo = normalizar(item.get("municipio") or "")
        if alvo and not any(normalizar(m) == alvo for m in municipios):
            return False
        if not alvo:
            return False
    piso = config.get("valor_minimo") or 0
    valor = item.get("valor_estimado")
    if piso and valor is not None and valor < piso:
        return False
    return True


def _duplicata_pncp(con, item):
    """Evita duplicar no mural do TCE o que já veio do PNCP (mesmo objeto)."""
    if item["fonte"] != "tcepi" or not item.get("objeto"):
        return False
    chave = normalizar(item["objeto"])[:120]
    for linha in con.execute(
            "SELECT objeto FROM licitacoes WHERE fonte='pncp' AND uf='PI'"):
        if normalizar(linha["objeto"] or "")[:120] == chave:
            return True
    return False


def executar(enviar_digest=True):
    config = cfg_mod.carregar()
    con = db_mod.conectar()
    novos, avaliados = [], 0

    fontes = [("PNCP", pncp.coletar)]
    if (config.get("tcepi") or {}).get("habilitado", True):
        fontes.append(("TCE-PI", tcepi.coletar))

    for nome, coletar in fontes:
        print(f"Coletando {nome}...")
        try:
            for item in coletar(config):
                avaliados += 1
                categoria, termos = classificar(item.get("objeto") or "", config)
                if not categoria or not _passa_filtros(item, config):
                    continue
                if _duplicata_pncp(con, item):
                    continue
                item["categoria"], item["termos_casados"] = categoria, termos
                if db_mod.upsert(con, item):
                    novos.append(item)
            con.commit()
        except Exception:
            print(f"  AVISO: coletor {nome} falhou — seguindo com as demais fontes")
            traceback.print_exc(limit=2)

    print(f"\n{avaliados} licitações avaliadas; {len(novos)} novas no radar.")

    if enviar_digest:
        pendentes = con.execute(
            "SELECT * FROM licitacoes WHERE notificado=0 AND status='novo' "
            "ORDER BY data_encerramento").fetchall()
        enviar(config, [dict(p) for p in pendentes])
        con.execute("UPDATE licitacoes SET notificado=1 WHERE notificado=0")
        con.commit()
    con.close()


if __name__ == "__main__":
    executar(enviar_digest="--sem-email" not in sys.argv)
