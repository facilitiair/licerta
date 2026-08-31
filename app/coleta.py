"""Motor de coleta (SPEC §5): baixa do PNCP, faz upsert e roda o matcher."""
import logging
import threading
from datetime import datetime

import requests

from .config import agora, config
from .db import Ata, ColetaLog, Licitacao, PerfilBusca, PerfilMatch, Sessao
from .documentos import baixar_arquivos
from .matcher import licitacao_casa_perfil, normalizar, texto_casa
from .pncp import MODALIDADES, atas_atualizadas, propostas_abertas
from .tcepi import coletar_mural

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
    combos = [(uf, m) for uf in lista_ufs for m in sorted(modalidades)]
    # Com o Mural TCE-PI ativo, o PI é varrido em TODAS as modalidades:
    # barato (uma UF) e essencial para deduplicar o mural contra o PNCP
    if not brasil_inteiro and "PI" in ufs:
        combos += [("PI", m) for m in MODALIDADES if m not in modalidades]
    return combos


def _upsert(sessao_db, item):
    """Insere ou atualiza por numero_controle_pncp. Retorna a licitação."""
    lic = sessao_db.query(Licitacao).filter_by(
        numero_controle_pncp=item["numero_controle_pncp"]).first()
    if lic:
        for campo, valor in item.items():
            setattr(lic, campo, valor)
        lic.coletado_em = agora()
    else:
        lic = Licitacao(**item)
        sessao_db.add(lic)
    return lic


def _rodar_matcher(sessao_db, perfis):
    """Cria perfil_matches que ainda não existem. Retorna ids das licitações
    recém-casadas (para o download automático de editais)."""
    novos_ids = []
    existentes = {(m.perfil_id, m.licitacao_id)
                  for m in sessao_db.query(PerfilMatch.perfil_id,
                                           PerfilMatch.licitacao_id)}
    licitacoes = sessao_db.query(Licitacao).all()
    for perfil in perfis:
        for lic in licitacoes:
            if (perfil.id, lic.id) in existentes:
                continue
            if licitacao_casa_perfil(lic, perfil):
                # registra POR QUAIS palavras casou, para exibir na interface
                _, termos = texto_casa(lic.objeto or "",
                                       perfil.palavras_incluir,
                                       perfil.palavras_excluir,
                                       getattr(perfil, "modo_busca", "ou"))
                sessao_db.add(PerfilMatch(perfil_id=perfil.id,
                                          licitacao_id=lic.id,
                                          termos=", ".join(termos)))
                novos_ids.append(lic.id)
                if len(novos_ids) % 200 == 0:
                    sessao_db.commit()   # lotes pequenos, mesmo motivo
    return novos_ids


def chaves_dedup_pncp(sessao_db):
    """Assinaturas das licitações do PNCP/PI para deduplicar o mural do TCE.

    O mesmo edital aparece com textos diferentes nos dois sistemas, então
    além do objeto usamos (município, valor exato) e (município, data da
    sessão, valor) como assinaturas alternativas.
    """
    chaves = set()
    linhas = sessao_db.query(
        Licitacao.objeto, Licitacao.municipio_nome,
        Licitacao.valor_total_estimado, Licitacao.data_encerramento_proposta
    ).filter(Licitacao.fonte == "pncp", Licitacao.uf == "PI")
    for objeto, municipio, valor, encerramento in linhas:
        chaves.add(("obj", _objeto_comparavel(objeto)))
        if municipio and valor:
            chaves.add(("mv", normalizar(municipio), f"{valor:.2f}"))
    return chaves


def _objeto_comparavel(objeto):
    """Remove o prefixo de plataforma ('[LICITANET] - ' etc.) e normaliza —
    o PNCP prefixa o objeto e o mural do TCE não."""
    import re
    limpo = re.sub(r"^\s*\[[^\]]{1,40}\]\s*-?\s*", "", objeto or "")
    return normalizar(limpo)[:110]


def e_duplicata_tcepi(item, chaves):
    """Item do mural já existe no PNCP? (por objeto OU município+valor)."""
    if ("obj", _objeto_comparavel(item.get("objeto"))) in chaves:
        return True
    municipio, valor = item.get("municipio_nome"), item.get("valor_total_estimado")
    if municipio and valor and \
            ("mv", normalizar(municipio), f"{valor:.2f}") in chaves:
        return True
    return False


def _coletar_tcepi(sessao_db, perfis, erros):
    """Mural TCE-PI (melhor esforço): só roda se algum perfil cobrir o PI."""
    if not any(not p.ufs or "PI" in p.ufs for p in perfis):
        return
    chaves = chaves_dedup_pncp(sessao_db)
    qtd = 0
    try:
        for item in coletar_mural(dias_futuro=config.DIAS_JANELA_FUTURA):
            if e_duplicata_tcepi(item, chaves):
                continue
            _upsert(sessao_db, item)
            qtd += 1
        sessao_db.commit()
        log.info("Mural TCE-PI: %s registros próprios", qtd)
    except Exception as e:  # noqa: BLE001 — fonte complementar nunca derruba
        sessao_db.rollback()
        erros.append(f"Mural TCE-PI: {e}")
        log.warning("Mural TCE-PI falhou: %s", e)


def _coletar_atas(sessao_db, perfis, erros):
    """Atas de registro de preços: varredura incremental + filtro por palavras.

    Guardamos apenas atas que casam com um perfil COM palavras-chave —
    sem esse recorte seriam centenas de milhares de atas vigentes.
    """
    perfis_com_palavras = [p for p in perfis if p.palavras_incluir]
    if not perfis_com_palavras:
        return
    primeira_vez = sessao_db.query(Ata).count() == 0
    dias = 30 if primeira_vez else 2
    qtd = 0
    try:
        hoje_iso = agora().strftime("%Y-%m-%d")
        for ata in atas_atualizadas(dias_retro=dias):
            if ata["cancelado"] or not ata["numero_controle_ata"]:
                continue
            # o endpoint devolve qualquer ata ALTERADA no período, inclusive
            # antigas — só interessam as ainda vigentes
            if (ata["vigencia_fim"] or "") < hoje_iso:
                continue
            casados = [p.nome for p in perfis_com_palavras
                       if texto_casa(ata["objeto"] or "", p.palavras_incluir,
                                     p.palavras_excluir,
                                     getattr(p, "modo_busca", "ou"))[0]]
            if not casados:
                continue
            existente = sessao_db.query(Ata).filter_by(
                numero_controle_ata=ata["numero_controle_ata"]).first()
            if existente:
                for campo, valor in ata.items():
                    setattr(existente, campo, valor)
                existente.perfis_casados = casados
            else:
                sessao_db.add(Ata(**ata, perfis_casados=casados))
                qtd += 1
            if qtd and qtd % 200 == 0:
                sessao_db.commit()       # lotes pequenos, mesmo motivo
        sessao_db.commit()
        log.info("Atas: %s novas compatíveis (janela de %s dias)", qtd, dias)
    except Exception as e:  # noqa: BLE001
        sessao_db.rollback()
        erros.append(f"atas: {e}")
        log.warning("Coleta de atas falhou: %s", e)


def _baixar_editais_novos(sessao_db, novos_ids, erros):
    """Download automático dos documentos das licitações recém-casadas."""
    total = 0
    for lic_id in dict.fromkeys(novos_ids):
        lic = sessao_db.get(Licitacao, lic_id)
        try:
            total += baixar_arquivos(sessao_db, lic)
        except Exception as e:  # noqa: BLE001
            erros.append(f"download edital lic {lic_id}: {e}")
    if total:
        log.info("Editais: %s arquivos baixados", total)


def coletar():
    """Rotina completa. Nenhuma exceção escapa — tudo vai para coletas_log."""
    if not _coletando.acquire(blocking=False):
        log.info("Coleta já em andamento; ignorando novo disparo")
        return None
    sessao_db = Sessao()
    registro = ColetaLog(inicio=agora())
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
                        if qtd % 200 == 0:
                            # lotes pequenos: libera o banco para os cliques
                            # do usuário passarem no meio da coleta
                            sessao_db.commit()
                sessao_db.commit()
                log.info("PNCP %s modalidade %s: %s registros",
                         uf or "BR", modalidade, qtd)
            except Exception as e:  # noqa: BLE001 — segue para a próxima combinação
                sessao_db.rollback()
                msg = f"{uf or 'BR'}/mod {modalidade}: {e}"
                erros.append(msg)
                log.error("Falha na combinação %s", msg)
        _coletar_tcepi(sessao_db, perfis, erros)
        novos_ids = _rodar_matcher(sessao_db, perfis)
        novas = len(novos_ids)
        sessao_db.commit()
        _coletar_atas(sessao_db, perfis, erros)
        _baixar_editais_novos(sessao_db, novos_ids, erros)
        registro.sucesso = len(erros) == 0
    except Exception as e:  # noqa: BLE001 — última linha de defesa
        sessao_db.rollback()
        erros.append(f"erro geral: {e}")
        registro.sucesso = False
        log.exception("Erro geral na coleta")
    finally:
        registro.fim = agora()
        registro.qtd_novas = novas
        registro.qtd_erros = len(erros)
        registro.detalhe_erro = "\n".join(erros)[:4000]
        sessao_db.commit()
        sessao_db.close()
        _coletando.release()
    return registro


def coletar_em_background():
    threading.Thread(target=coletar, daemon=True).start()
