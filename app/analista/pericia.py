"""Perícia completa — o analista sênior da plataforma (camada 3+).

O parecer rápido (parecer.py) é UMA chamada de modelo. Aqui o mesmo
material passa por um pipeline de especialistas, como no gabinete
pericial que deu origem à plataforma:

1. LEITOR DE CADERNO (extração): abre o dossiê documento a documento e
   devolve extração estruturada com denominador — sem opinião.
2. PERITOS (sob demanda, só quando há material): qualificação técnica
   (atestados/CATs/registro no conselho) e econômico-financeira
   (balanço × contrato social), cada um com seu laudo.
3. SÍNTESE (modelo forte): o parecer final recebe o edital, a ficha, os
   prazos calculados por código, o dossiê E os laudos dos peritos.

Demora minutos e custa alguns dólares — por isso roda em segundo plano
e cada etapa grava o custo. Os laudos completos vão como anexos do
parecer: o cliente vê o trabalho, não só a conclusão.
"""
import json
import logging
import os
import threading

from ia import camadas, cliente

from ..db import Parecer, Sessao
from ..editais.analise import _custo_da_ultima_chamada
from .parecer import LIMITE_EDITAL, ParecerIndevido, _base_juridica, \
    montar_insumos

log = logging.getLogger("radar.analista")

TIPOS_TECNICOS = {"Atestado de Capacidade", "CAT", "Registro CREA/CAU"}
TIPOS_CONTABEIS = {"Balanço Patrimonial", "Contrato Social"}
SEM_TEXTO = "(sem texto legível"

# Uma perícia por licitação de cada vez — clique duplo não paga duas.
_em_andamento = set()
_trava = threading.Lock()


def _referencias(*nomes):
    partes = []
    for nome in nomes:
        try:
            caminho = os.path.join(cliente.RAIZ_IA, "referencias",
                                   f"{nome}.md")
            with open(caminho, encoding="utf-8") as f:
                partes.append(f.read())
        except OSError:
            log.warning("Referência %s ausente — perícia segue sem ela",
                        nome)
    return "\n\n---\n\n".join(partes)


def _chamar(job, prompt, mensagem, modelo, custos):
    texto = cliente.chamar(job=job,
                           prompt_sistema=cliente.carregar_prompt(prompt),
                           mensagem=mensagem, modelo=modelo,
                           max_tokens=16000)
    custos.append(_custo_da_ultima_chamada())
    return texto


def gerar_pericia(sessao_db, lic, usuario=None, hoje=None):
    """Roda o pipeline completo e grava UM Parecer com os laudos anexos."""
    usuario_id = getattr(usuario, "id", None)
    insumos = montar_insumos(sessao_db, lic, hoje, usuario_id=usuario_id)
    entrada = insumos["entrada"]
    data_sessao = (insumos["data_sessao"].strftime("%d/%m/%Y")
                   if insumos["data_sessao"] else "não informada")
    custos = []
    dossie = entrada["dossie"]
    legiveis = [d for d in dossie
                if SEM_TEXTO not in d["texto_extraido"]]

    # 1) leitor de caderno — extração estruturada do dossiê
    extracao = None
    if legiveis:
        extracao = _chamar(
            "pericia_leitor", "peritos/leitor-caderno",
            json.dumps({
                "contexto_do_lote": ("dossiê da empresa cliente para o "
                                     f"certame {lic.objeto!r}"),
                "denominador_do_lote": (
                    f"{len(dossie)} documentos ativos no dossiê; "
                    f"{len(legiveis)} com texto legível enviados neste "
                    "lote (integral); os demais estão pendentes de OCR"),
                "documentos_do_caso": legiveis,
            }, ensure_ascii=False), camadas.EXTRACAO, custos)

    ficha = entrada.get("ficha_analisada") or {}
    habilitacao = ficha.get("habilitacao") or {}
    laudos = []

    # 1b) exame técnico por código — hash, formato real, revisões,
    # metadados, assinatura (a bancada forense determinística)
    from .exame import examinar_dossie
    try:
        exame_tecnico = examinar_dossie(sessao_db, dossie, usuario_id)
    except Exception:  # noqa: BLE001 — exame é cortesia, nunca derruba
        log.exception("Exame técnico do dossiê falhou")
        exame_tecnico = {}

    contexto_certame = {"objeto": lic.objeto, "orgao": lic.orgao_nome,
                        "municipio": lic.municipio_nome, "uf": lic.uf,
                        "data_da_sessao": data_sessao}

    # 2·pré) perito documental — coerência formal/cronológica do caderno
    if legiveis:
        laudo = _chamar(
            "pericia_documental", "peritos/perito-documental",
            json.dumps({
                "parte_examinada": "empresa_cliente",
                "documentos_do_caso": legiveis,
                "exame_tecnico": exame_tecnico,
                "contexto_do_certame": contexto_certame,
            }, ensure_ascii=False), camadas.GERACAO, custos)
        laudos.append(("Laudo do perito documental "
                       "(coerência formal e cronológica)", laudo))

    # 2a) perito de atestados — só com material técnico no dossiê
    tecnicos = [d for d in legiveis if d["tipo"] in TIPOS_TECNICOS]
    if tecnicos:
        laudo = _chamar(
            "pericia_atestados", "peritos/perito-atestados",
            json.dumps({
                "parte_examinada": "empresa_cliente",
                "dossie_empresa": {"empresa": entrada["empresa"],
                                   "extracao_do_leitor": extracao},
                "documentos_do_caso": tecnicos,
                "ficha_edital": habilitacao.get("tecnica")
                or "exigência técnica não extraída — aplicar o roteiro "
                   "geral e sinalizar a lacuna",
                "data_da_sessao": data_sessao,
                "ramo_da_empresa_cliente": entrada["empresa"],
            }, ensure_ascii=False), camadas.GERACAO, custos)
        laudos.append(("Laudo do perito de atestados "
                       "(qualificação técnica)", laudo))

    # 2b) perito contábil — só com balanço no dossiê
    contabeis = [d for d in legiveis if d["tipo"] in TIPOS_CONTABEIS]
    if any(d["tipo"] == "Balanço Patrimonial" for d in contabeis):
        laudo = _chamar(
            "pericia_contabil", "peritos/perito-contabil",
            json.dumps({
                "parte_examinada": "empresa_cliente",
                "dossie_empresa": {"empresa": entrada["empresa"],
                                   "extracao_do_leitor": extracao},
                "documentos_do_caso": contabeis,
                "ficha_edital": habilitacao.get("economico_financeira")
                or "exigência econômico-financeira não extraída — aplicar "
                   "o roteiro geral e sinalizar a lacuna",
                "data_da_sessao": data_sessao,
                "data_de_hoje": entrada["data_de_hoje"],
                "base_normativa": _referencias(
                    "contabilidade-habilitacao", "base-normativa-contabil"),
            }, ensure_ascii=False), camadas.GERACAO, custos)
        laudos.append(("Laudo do perito contábil "
                       "(econômico-financeira)", laudo))

    # 3) contraditório — o adversário interno tenta derrubar cada achado
    secao_laudos = "\n\n".join(
        f"### {titulo}\n\n{laudo}" for titulo, laudo in laudos) \
        or "(nenhum perito acionado — dossiê sem material técnico/contábil)"
    contraditorio = None
    if laudos:
        contraditorio = _chamar(
            "pericia_contraditorio", "peritos/perito-contraditor",
            json.dumps({"contexto_do_certame": contexto_certame},
                       ensure_ascii=False)
            + "\n\nLAUDOS A REFUTAR:\n\n" + secao_laudos
            + "\n\nTRECHOS DO EDITAL:\n\n"
            + (insumos["texto_edital"][:80_000] or "(sem texto)"),
            camadas.GERACAO, custos)

    # 4) síntese no modelo forte, com laudos E contraditório como insumo
    mensagem = (
        json.dumps(entrada, ensure_ascii=False, indent=1)
        + "\n\nLAUDOS DOS PERITOS (insumo verificado — incorpore as "
        "conclusões e cite os achados relevantes):\n\n" + secao_laudos
        + "\n\nCONTRADITÓRIO (vereditos do perito adversário — achado "
        "`derrubado` NÃO entra no parecer; `enfraquecido` entra com a "
        "ressalva; `sobrevive` entra com a confiança que restou):\n\n"
        + (contraditorio or "(sem laudos a contraditar)")
        + "\n\nBASE JURÍDICA:\n\n" + _base_juridica()
        + "\n\nTEXTO DO EDITAL E ANEXOS:\n\n"
        + (insumos["texto_edital"][:LIMITE_EDITAL]
           or "(sem texto legível — análise pela ficha)"))
    texto = _chamar("pericia_sintese", "parecer-edital", mensagem,
                    camadas.PERICIA, custos)

    # 5) revisão — controle de qualidade antes da entrega; correções
    # obrigatórias são aplicadas numa passada de edição barata
    revisao = _chamar(
        "pericia_revisao", "peritos/perito-revisor",
        json.dumps({"contexto": contexto_certame}, ensure_ascii=False)
        + "\n\nPARECER A REVISAR:\n\n" + texto
        + "\n\nLAUDOS DE ORIGEM:\n\n" + secao_laudos[:60_000]
        + "\n\nCONTRADITÓRIO:\n\n" + (contraditorio or "(não houve)"),
        camadas.GERACAO, custos)
    if "Correções obrigatórias:\n  nenhuma" not in revisao \
            and "VEREDITO: aprovado\n" not in revisao + "\n":
        texto = cliente.chamar(
            job="pericia_correcao",
            prompt_sistema=cliente.carregar_prompt("peritos/perito-corretor"),
            mensagem=("PARECER:\n\n" + texto
                      + "\n\nPARECER DE REVISÃO A APLICAR:\n\n" + revisao),
            modelo=camadas.GERACAO, max_tokens=16000)
        custos.append(_custo_da_ultima_chamada())
    if "Parecer gerado automaticamente" not in texto[:400]:
        texto = ("> Parecer gerado automaticamente pela plataforma — apoio "
                 "à decisão. Não substitui a leitura do edital nem "
                 "orientação jurídica.\n\n" + texto)
    if laudos:
        texto += ("\n\n---\n\n# Anexos — laudos dos peritos\n\n"
                  + "\n\n---\n\n".join(f"## {t}\n\n{l}" for t, l in laudos))
    if contraditorio:
        texto += ("\n\n---\n\n## Contraditório — tentativas de refutação "
                  "e vereditos\n\n" + contraditorio)
    parecer = Parecer(licitacao_id=lic.id, texto=texto,
                      modelo=f"{camadas.PERICIA} + peritos",
                      custo_usd=round(sum(custos), 4),
                      criado_por=getattr(usuario, "id", None))
    sessao_db.add(parecer)
    sessao_db.commit()
    log.info("Perícia completa da licitação %s: %s etapas, US$ %.4f",
             lic.id, len(custos), parecer.custo_usd)
    return parecer


def _rodar_em_fundo(lic_id, usuario_id):
    from ..db import Licitacao
    s = Sessao()
    try:
        lic = s.get(Licitacao, lic_id)
        usuario = type("U", (), {"id": usuario_id})() if usuario_id else None
        gerar_pericia(s, lic, usuario=usuario)
    except Exception as e:  # noqa: BLE001 — falha vira parecer visível
        log.exception("Perícia da licitação %s falhou", lic_id)
        s.rollback()
        s.add(Parecer(
            licitacao_id=lic_id, criado_por=usuario_id,
            modelo=f"{camadas.PERICIA} + peritos",
            texto=("> A perícia completa NÃO terminou desta vez — nenhum "
                   "resultado abaixo é análise.\n\nO que houve, em uma "
                   f"linha: {e}\n\nTente de novo em alguns minutos; o "
                   "custo das etapas concluídas está no diagnóstico.")))
        s.commit()
    finally:
        s.close()
        with _trava:
            _em_andamento.discard(lic_id)


def iniciar(sessao_db, lic, usuario=None, hoje=None):
    """Valida os insumos AGORA (erros aparecem na hora) e dispara a
    perícia em segundo plano. Devolve False se já há uma em andamento."""
    montar_insumos(sessao_db, lic, hoje,      # levanta cedo se faltar algo
                   usuario_id=getattr(usuario, "id", None))
    with _trava:
        if lic.id in _em_andamento:
            return False
        _em_andamento.add(lic.id)
    threading.Thread(target=_rodar_em_fundo,
                     args=(lic.id, getattr(usuario, "id", None)),
                     daemon=True).start()
    return True
