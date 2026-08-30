"""Motor de coleta (SPEC §5): baixa do PNCP, faz upsert e roda o matcher."""
import logging
import threading
from datetime import datetime

import requests

from .config import config
from .db import ColetaLog, Licitacao, PerfilBusca, PerfilMatch, Sessao
from .matcher import licitacao_casa_perfil
from .pncp import MODALIDADES, propostas_abertas

log = logging.getLogger("radar.coleta")

# Trava para o botão "Coletar agora" não disparar duas coletas ao mesmo tempo
_coletando = threading.Lock()


def coleta_em_andamento():
    if _coletando.acquire(blocking=False):
        _coletando.release()
        return False
    return True


def _combinacoes(perfis):
    """União dos perfis ativos: UFs distintas × modalidades distintas.
    Se algum perfil pedir Brasil inteiro (ufs vazio), consulta sem `uf`."""
    ufs, modalidades, brasil_inteiro = set(), set(), False
    for p in perfis:
        if p.ufs:
            ufs.update(p.ufs)
        else:
            brasil_inteiro = True
        modalidades.update(p.modalidades or MODALIDADES.keys())
    lista_ufs = [None] if brasil_inteiro else sorted(ufs)
    return [(uf, m) for uf in lista_ufs for m in sorted(modalidades)]


def _upsert(sessao_db, item):
    """Insere ou atualiza por numero_controle_pncp. Retorna a licitação."""
    lic = sessao_db.query(Licitacao).filter_by(
        numero_controle_pncp=item["numero_controle_pncp"]).first()
    if lic:
        for campo, valor in item.items():
            setattr(lic, campo, valor)
        lic.coletado_em = datetime.now()
    else:
        lic = Licitacao(**item)
        sessao_db.add(lic)
    return lic


def _rodar_matcher(sessao_db, perfis):
    """Cria perfil_matches que ainda não existem. Retorna qtd de novos."""
    novos = 0
    existentes = {(m.perfil_id, m.licitacao_id)
                  for m in sessao_db.query(PerfilMatch.perfil_id,
                                           PerfilMatch.licitacao_id)}
    licitacoes = sessao_db.query(Licitacao).all()
    for perfil in perfis:
        for lic in licitacoes:
            if (perfil.id, lic.id) in existentes:
                continue
            if licitacao_casa_perfil(lic, perfil):
                sessao_db.add(PerfilMatch(perfil_id=perfil.id, licitacao_id=lic.id))
                novos += 1
    return novos


def coletar():
    """Rotina completa. Nenhuma exceção escapa — tudo vai para coletas_log."""
    if not _coletando.acquire(blocking=False):
        log.info("Coleta já em andamento; ignorando novo disparo")
        return None
    sessao_db = Sessao()
    registro = ColetaLog(inicio=datetime.now())
    sessao_db.add(registro)
    sessao_db.commit()
    erros, novas = [], 0
    try:
        perfis = sessao_db.query(PerfilBusca).filter_by(ativo=True).all()
        if not perfis:
            erros.append("nenhum perfil ativo — nada a coletar")
        http = requests.Session()
        for uf, modalidade in _combinacoes(perfis):
            try:
                qtd = 0
                for item in propostas_abertas(
                        modalidade, uf=uf,
                        dias_futuro=config.DIAS_JANELA_FUTURA, sessao=http):
                    if item["numero_controle_pncp"]:
                        _upsert(sessao_db, item)
                        qtd += 1
                sessao_db.commit()
                log.info("PNCP %s modalidade %s: %s registros",
                         uf or "BR", modalidade, qtd)
            except Exception as e:  # noqa: BLE001 — segue para a próxima combinação
                sessao_db.rollback()
                msg = f"{uf or 'BR'}/mod {modalidade}: {e}"
                erros.append(msg)
                log.error("Falha na combinação %s", msg)
        novas = _rodar_matcher(sessao_db, perfis)
        sessao_db.commit()
        registro.sucesso = len(erros) == 0
    except Exception as e:  # noqa: BLE001 — última linha de defesa
        sessao_db.rollback()
        erros.append(f"erro geral: {e}")
        registro.sucesso = False
        log.exception("Erro geral na coleta")
    finally:
        registro.fim = datetime.now()
        registro.qtd_novas = novas
        registro.qtd_erros = len(erros)
        registro.detalhe_erro = "\n".join(erros)[:4000]
        sessao_db.commit()
        sessao_db.close()
        _coletando.release()
    return registro


def coletar_em_background():
    threading.Thread(target=coletar, daemon=True).start()
