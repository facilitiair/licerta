"""Higiene do banco: o radar coleta o Brasil inteiro e o arquivo cresce
sem parar — e este banco viaja para o GitHub (limite duro de 100 MB no
push) e vive num volume pago no Railway.

O que sai: licitação encerrada há mais de DIAS_RETER dias em que NINGUÉM
mexeu. Interação humana segura a linha: match favoritado, anotado ou
movido no funil, ou minuta gerada — isso é trabalho do usuário e não se
apaga por rotina. Atas vencidas e logs de coleta antigos também saem.
O VACUUM devolve o espaço ao arquivo (só quando a folga compensa).
"""
import logging
import os
import shutil

from datetime import timedelta

from ..config import PASTA_DADOS, config, hoje as hoje_local
from ..db import (ArquivoEdital, Ata, ColetaLog, EditalFicha, Licitacao,
                  LicitacaoAlteracao, Minuta, PerfilMatch, engine)

log = logging.getLogger("radar.limpeza")

MANTER_LOGS = 300


def _ids_intocados(sessao_db, corte_iso):
    """Licitações encerradas antes do corte SEM marca de gente."""
    encerradas = (sessao_db.query(Licitacao.id)
                  .filter(Licitacao.data_encerramento_proposta.isnot(None),
                          Licitacao.data_encerramento_proposta < corte_iso))
    ids = {i for (i,) in encerradas}
    if not ids:
        return ids
    tocados = (sessao_db.query(PerfilMatch.licitacao_id)
               .filter(PerfilMatch.licitacao_id.in_(ids))
               .filter((PerfilMatch.favorito.is_(True))
                       | (PerfilMatch.anotacao != "")
                       | (PerfilMatch.status != "novo")))
    ids -= {i for (i,) in tocados}
    com_minuta = (sessao_db.query(Minuta.licitacao_id)
                  .filter(Minuta.licitacao_id.in_(ids)))
    ids -= {i for (i,) in com_minuta}
    return ids


def limpar(sessao_db, hoje=None, vacuum=True):
    """Roda a faxina. Devolve contadores (para o log da coleta)."""
    hoje = hoje or hoje_local()
    dias = getattr(config, "DIAS_RETER_ENCERRADAS", 30)
    corte = (hoje - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M")
    ids = _ids_intocados(sessao_db, corte)
    contadores = {"licitacoes": 0, "atas": 0, "logs": 0}
    for lic_id in ids:
        # arquivos físicos primeiro — linha sem arquivo é recuperável,
        # arquivo sem linha é lixo eterno no volume
        pasta = os.path.join(PASTA_DADOS, "editais", str(lic_id))
        if os.path.isdir(pasta):
            shutil.rmtree(pasta, ignore_errors=True)
        for modelo in (ArquivoEdital, EditalFicha, LicitacaoAlteracao,
                       PerfilMatch):
            sessao_db.query(modelo).filter_by(licitacao_id=lic_id).delete()
        sessao_db.query(Licitacao).filter_by(id=lic_id).delete()
        contadores["licitacoes"] += 1
        if contadores["licitacoes"] % 500 == 0:
            sessao_db.commit()            # lotes: não segurar o banco
    corte_ata = (hoje - timedelta(days=30)).strftime("%Y-%m-%d")
    contadores["atas"] = (sessao_db.query(Ata)
                          .filter(Ata.vigencia_fim.isnot(None),
                                  Ata.vigencia_fim < corte_ata)
                          .delete(synchronize_session=False))
    sobreviventes = [i for (i,) in
                     sessao_db.query(ColetaLog.id)
                     .order_by(ColetaLog.inicio.desc()).limit(MANTER_LOGS)]
    if sobreviventes:
        contadores["logs"] = (sessao_db.query(ColetaLog)
                              .filter(~ColetaLog.id.in_(sobreviventes))
                              .delete(synchronize_session=False))
    sessao_db.commit()
    if any(contadores.values()):
        log.info("Faxina: %s licitações encerradas, %s atas vencidas e %s "
                 "logs antigos removidos", contadores["licitacoes"],
                 contadores["atas"], contadores["logs"])
    if vacuum:
        contadores["vacuum"] = _vacuum_se_compensar()
    return contadores


def _vacuum_se_compensar(minimo_paginas_livres=0.08):
    """VACUUM só quando a folga passa de ~8% do arquivo — reescrever 70 MB
    a cada coleta para ganhar 200 KB é desperdício de I/O do volume."""
    try:
        with engine.connect().execution_options(
                isolation_level="AUTOCOMMIT") as con:
            livres = con.exec_driver_sql("PRAGMA freelist_count").scalar()
            total = con.exec_driver_sql("PRAGMA page_count").scalar()
            if not total or livres / total < minimo_paginas_livres:
                return False
            con.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            con.exec_driver_sql("VACUUM")
            log.info("VACUUM: %s de %s páginas estavam livres", livres, total)
            return True
    except Exception:  # noqa: BLE001 — faxina nunca derruba a coleta
        log.exception("VACUUM falhou")
        return False
