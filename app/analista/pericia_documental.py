"""Perito documental — exame do caderno de um TERCEIRO (concorrente).

Mesmo gabinete da perícia completa, apontado para fora: exame técnico
por código, leitor de caderno, perito documental, peritos condicionais,
contraditório, síntese em formulação indiciária e revisão. Recurso do
plano premium; roda em segundo plano como a perícia.
"""
import json
import logging
import os
import threading

from ia import camadas, cliente

from ..config import PASTA_DADOS
from ..db import CasoPericial, DocumentoCaso, LaudoPericial, Sessao
from ..documentos.checklist import tipo_do_conteudo
from ..editais.analise import _custo_da_ultima_chamada
from .exame import examinar_pdf
from .parecer import LIMITE_POR_DOCUMENTO, ParecerIndevido, e_pdf
from .pericia import _chamar as _chamar_pericia

log = logging.getLogger("radar.analista")

PASTA_CASOS = os.path.join(PASTA_DADOS, "casos")
MAX_DOCS_POR_CASO = 40
TIPOS_TECNICOS = {"Atestado de Capacidade", "CAT", "Registro CREA/CAU"}

_em_andamento = set()
_trava = threading.Lock()


def _texto_documento(doc):
    caminho = os.path.join(PASTA_DADOS, doc.caminho_local or "")
    if not (doc.caminho_local and os.path.exists(caminho) and e_pdf(caminho)):
        return None
    try:
        from ia import ocr
        # Caderno de concorrente costuma vir digitalizado: visão, com cache
        texto, _ = ocr.texto_do_pdf(caminho, max_paginas=40,
                                    job="ocr_caderno", max_paginas_nativo=30)
        texto = texto.strip()
        return texto[:LIMITE_POR_DOCUMENTO] if len(texto) >= 100 else None
    except Exception:  # noqa: BLE001 — ilegível vira "não verificado"
        return None


def montar_caderno(sessao_db, caso):
    """Texto + exame técnico de cada documento do caso."""
    docs = (sessao_db.query(DocumentoCaso)
            .filter_by(caso_id=caso.id).all())
    if not docs:
        raise ParecerIndevido(
            "O caso ainda não tem documentos — suba os arquivos do "
            "caderno antes de pedir o laudo.")
    caderno, exames = [], {}
    for d in docs:
        texto = _texto_documento(d)
        item = {"nome": d.nome,
                "tipo": (tipo_do_conteudo(texto or "") or "Outro"),
                "texto_extraido": texto or
                "(sem texto legível — tratar como não verificado; "
                "possível digitalização pendente de OCR)"}
        caderno.append(item)
        exame = examinar_pdf(d.caminho_local, texto=texto)
        if exame:
            exames[d.nome] = exame
    return caderno, exames


def gerar_laudo(sessao_db, caso, usuario=None):
    """Roda o pipeline pericial sobre o caso e grava o LaudoPericial."""
    cliente.exigir_chave()
    caderno, exames = montar_caderno(sessao_db, caso)
    legiveis = [d for d in caderno
                if "sem texto legível" not in d["texto_extraido"]]
    if not legiveis:
        # Sem texto não há perícia: seguir adiante gastava síntese e
        # revisão (os modelos mais caros) para um laudo vazio.
        raise ParecerIndevido(
            "Nenhum documento do caderno tem texto legível, nem pela leitura "
            "por imagem — confira se as páginas estão nítidas e inteiras.")
    custos = []
    contexto = {"titulo": caso.titulo, "observacao": caso.observacao,
                "parte_examinada": "concorrente"}

    extracao = None
    if legiveis:
        extracao = _chamar_pericia(
            "laudo_leitor", "peritos/leitor-caderno",
            json.dumps({
                "contexto_do_lote": f"caderno de terceiro: {caso.titulo}",
                "denominador_do_lote": (
                    f"{len(caderno)} documentos no caso; {len(legiveis)} "
                    "com texto legível (lote integral); os demais "
                    "pendentes de OCR"),
                "documentos_do_caso": legiveis,
            }, ensure_ascii=False), camadas.EXTRACAO, custos)

    laudos = []
    if legiveis:
        laudos.append(("Perito documental", _chamar_pericia(
            "laudo_documental", "peritos/perito-documental",
            json.dumps({"parte_examinada": "concorrente",
                        "documentos_do_caso": legiveis,
                        "exame_tecnico": exames,
                        "contexto_do_certame": contexto},
                       ensure_ascii=False), camadas.GERACAO, custos)))
    tecnicos = [d for d in legiveis if d["tipo"] in TIPOS_TECNICOS]
    if tecnicos:
        laudos.append(("Perito de atestados", _chamar_pericia(
            "laudo_atestados", "peritos/perito-atestados",
            json.dumps({"parte_examinada": "concorrente",
                        "dossie_empresa": {"extracao_do_leitor": extracao},
                        "documentos_do_caso": tecnicos,
                        "ficha_edital": "exigência do edital não fornecida "
                        "— aplicar o roteiro geral e sinalizar a lacuna",
                        "data_da_sessao": "não informada",
                        "ramo_da_empresa_cliente": "não informado"},
                       ensure_ascii=False), camadas.GERACAO, custos)))
    if any(d["tipo"] == "Balanço Patrimonial" for d in legiveis):
        laudos.append(("Perito contábil", _chamar_pericia(
            "laudo_contabil", "peritos/perito-contabil",
            json.dumps({"parte_examinada": "concorrente",
                        "dossie_empresa": {"extracao_do_leitor": extracao},
                        "documentos_do_caso":
                            [d for d in legiveis
                             if d["tipo"] == "Balanço Patrimonial"],
                        "ficha_edital": "exigência não fornecida",
                        "data_da_sessao": "não informada",
                        "data_de_hoje": "", "base_normativa": ""},
                       ensure_ascii=False), camadas.GERACAO, custos)))

    secao_laudos = "\n\n".join(
        f"### {t}\n\n{l}" for t, l in laudos) or "(caderno sem texto legível)"
    contraditorio = None
    if laudos:
        contraditorio = _chamar_pericia(
            "laudo_contraditorio", "peritos/perito-contraditor",
            json.dumps({"contexto_do_certame": contexto},
                       ensure_ascii=False)
            + "\n\nLAUDOS A REFUTAR:\n\n" + secao_laudos,
            camadas.GERACAO, custos)

    mensagem = (json.dumps({"contexto_do_caso": contexto},
                           ensure_ascii=False)
                + "\n\nLAUDOS DOS PERITOS:\n\n" + secao_laudos
                + "\n\nCONTRADITÓRIO (derrubado NÃO entra; enfraquecido "
                "com ressalva):\n\n" + (contraditorio or "(não houve)")
                + "\n\nEXAME TÉCNICO POR CÓDIGO:\n\n"
                + json.dumps(exames, ensure_ascii=False))
    texto = _chamar_pericia("laudo_sintese", "laudo-pericial", mensagem,
                            camadas.PERICIA, custos)

    revisao = _chamar_pericia(
        "laudo_revisao", "peritos/perito-revisor",
        json.dumps({"contexto": contexto}, ensure_ascii=False)
        + "\n\nPARECER A REVISAR:\n\n" + texto
        + "\n\nLAUDOS DE ORIGEM:\n\n" + secao_laudos[:60_000]
        + "\n\nCONTRADITÓRIO:\n\n" + (contraditorio or "(não houve)"),
        camadas.GERACAO, custos)
    if "Correções obrigatórias:\n  nenhuma" not in revisao \
            and "VEREDITO: aprovado\n" not in revisao + "\n":
        texto = cliente.chamar(
            job="laudo_correcao",
            prompt_sistema=cliente.carregar_prompt("peritos/perito-corretor"),
            mensagem=("LAUDO:\n\n" + texto
                      + "\n\nPARECER DE REVISÃO:\n\n" + revisao),
            modelo=camadas.GERACAO, max_tokens=16000)
        custos.append(_custo_da_ultima_chamada())

    if "Laudo preliminar gerado automaticamente" not in texto[:400]:
        texto = ("> Laudo preliminar gerado automaticamente pela "
                 "plataforma — apoio à decisão. Não substitui perícia "
                 "formal por profissional habilitado nem orientação "
                 "jurídica.\n\n" + texto)
    if contraditorio:
        texto += ("\n\n---\n\n## Contraditório — tentativas de refutação "
                  "e vereditos\n\n" + contraditorio)

    laudo = LaudoPericial(caso_id=caso.id, texto=texto,
                          modelo=f"{camadas.PERICIA} + peritos",
                          custo_usd=round(sum(custos), 4),
                          criado_por=getattr(usuario, "id", None))
    sessao_db.add(laudo)
    sessao_db.commit()
    log.info("Laudo pericial do caso %s: %s etapas, US$ %.4f",
             caso.id, len(custos), laudo.custo_usd)
    return laudo


def _rodar_em_fundo(caso_id, usuario_id):
    s = Sessao()
    try:
        caso = s.get(CasoPericial, caso_id)
        usuario = type("U", (), {"id": usuario_id})() if usuario_id else None
        gerar_laudo(s, caso, usuario=usuario)
    except Exception as e:  # noqa: BLE001 — falha vira laudo visível
        log.exception("Laudo do caso %s falhou", caso_id)
        s.rollback()
        s.add(LaudoPericial(
            caso_id=caso_id, criado_por=usuario_id,
            modelo=f"{camadas.PERICIA} + peritos",
            texto=("> O laudo NÃO terminou desta vez — nada abaixo é "
                   f"análise.\n\nO que houve, em uma linha: {e}\n\n"
                   "Tente de novo em alguns minutos.")))
        s.commit()
    finally:
        s.close()
        with _trava:
            _em_andamento.discard(caso_id)


def iniciar(sessao_db, caso, usuario=None):
    """Valida agora, roda em segundo plano. False = já em andamento."""
    cliente.exigir_chave()
    montar_caderno(sessao_db, caso)      # levanta cedo se faltar material
    with _trava:
        if caso.id in _em_andamento:
            return False
        _em_andamento.add(caso.id)
    threading.Thread(target=_rodar_em_fundo,
                     args=(caso.id, getattr(usuario, "id", None)),
                     daemon=True).start()
    return True
