"""O analista pericial da plataforma (camada 3 — perícia sob demanda).

Portado do analista de licitações original: parecer completo que cruza o
edital inteiro com o DOSSIÊ real da empresa — lendo o texto dos próprios
PDFs das certidões e atestados, não só os rótulos — sobre a base
jurídica (Lei 14.133 + jurisprudência consolidada), no modelo forte.

O que continua sendo código, nunca IA: os prazos entram calculados
(acompanhamento/prazos) e a validade de cada documento é aferida na data
da sessão antes de chegar ao prompt.
"""
import json
import logging
import os

from ia import camadas, cliente

from ..acompanhamento.prazos import prazos_da_sessao
from ..config import PASTA_DADOS, hoje as hoje_local
from ..db import ArquivoEdital, DocumentoEmpresa, EditalFicha, Parecer
from ..documentos.checklist import data_da_sessao
from ..editais.analise import extrair_texto_pdfs, _custo_da_ultima_chamada

log = logging.getLogger("radar.analista")

# Teto de leitura dos documentos do dossiê: perícia lê o documento, mas
# um balanço de 300 páginas não precisa entrar inteiro em cada parecer.
LIMITE_POR_DOCUMENTO = 12_000
LIMITE_DOSSIE = 60_000
LIMITE_EDITAL = 250_000


class ParecerIndevido(RuntimeError):
    """Situação em que gerar o parecer seria desperdício — a mensagem
    explica o que fazer antes."""


def _texto_documento(doc):
    """Texto de um PDF do dossiê (melhor esforço; imagem = None)."""
    caminho = os.path.join(PASTA_DADOS, doc.caminho_local or "")
    if not (doc.caminho_local and caminho.lower().endswith(".pdf")
            and os.path.exists(caminho)):
        return None
    try:
        from pypdf import PdfReader
        texto = "\n".join((p.extract_text() or "")
                          for p in PdfReader(caminho).pages[:20])
        texto = texto.strip()
        return texto[:LIMITE_POR_DOCUMENTO] if len(texto) >= 100 else None
    except Exception:  # noqa: BLE001 — dossiê ilegível vira "não verificado"
        return None


def _dossie(sessao_db, data_sessao):
    """O dossiê como o prompt recebe: rótulo + validade NA SESSÃO + texto."""
    docs = (sessao_db.query(DocumentoEmpresa)
            .filter_by(arquivado=False).all())
    itens, usado = [], 0
    for d in docs:
        situacao = "sem validade informada"
        if d.validade:
            if data_sessao and d.validade < data_sessao.isoformat():
                situacao = f"VENCIDO na data da sessão (validade {d.validade})"
            else:
                situacao = f"válido até {d.validade}"
        texto = _texto_documento(d) if usado < LIMITE_DOSSIE else None
        if texto:
            usado += len(texto)
        itens.append({"nome": d.nome, "tipo": d.tipo,
                      "validade_na_sessao": situacao,
                      "texto_extraido": texto or
                      "(sem texto legível — tratar como não verificado)"})
    return itens


def _base_juridica():
    """Lei resumida + jurisprudência + glossário — o dente do parecer."""
    partes = []
    for nome in ("lei-14133-2021", "jurisprudencia", "glossario"):
        try:
            caminho = os.path.join(cliente.RAIZ_IA, "referencias",
                                   f"{nome}.md")
            with open(caminho, encoding="utf-8") as f:
                partes.append(f.read())
        except OSError:
            log.warning("Referência %s ausente — parecer segue sem ela", nome)
    return "\n\n---\n\n".join(partes)


def montar_insumos(sessao_db, lic, hoje=None):
    """Reúne tudo que uma perícia precisa: edital, ficha, prazos por
    código, dossiê com validade aferida na sessão. Usado pelo parecer
    rápido e pela perícia completa (analista/pericia.py).

    Levanta ParecerIndevido quando faltam insumos e SemChaveIA quando a
    análise automática está desligada.
    """
    hoje = hoje or hoje_local()
    cliente.exigir_chave()
    arquivos = (sessao_db.query(ArquivoEdital)
                .filter_by(licitacao_id=lic.id).all())
    texto_edital, _ = extrair_texto_pdfs(arquivos)
    ficha = (sessao_db.query(EditalFicha)
             .filter_by(licitacao_id=lic.id).first())
    dados_ficha = None
    if ficha and ficha.ficha_json:
        try:
            dados_ficha = json.loads(ficha.ficha_json)
        except ValueError:
            pass
    if not texto_edital and not dados_ficha:
        raise ParecerIndevido(
            "Sem material para a perícia: os documentos deste edital não "
            "têm texto legível e ainda não há ficha. Gere a ficha primeiro "
            "(botão Analisar edital) ou abra os documentos pelo link.")

    sessao_data = data_da_sessao(dados_ficha, lic)
    prazos = prazos_da_sessao(sessao_data, hoje)
    prazo_texto = "Data da sessão não informada — conferir manualmente."
    if prazos:
        if prazos["sessao_passou"]:
            prazo_texto = "A SESSÃO JÁ PASSOU."
        else:
            prazo_texto = (
                f"{prazos['dias_uteis_restantes']} dia(s) útil(eis) até a "
                f"sessão ({sessao_data.strftime('%d/%m/%Y')}); impugnação/"
                "esclarecimento até "
                f"{prazos['limite_impugnacao'].strftime('%d/%m/%Y')} "
                "(3 dias úteis antes, art. 164; feriado local do órgão "
                "pode recuar as datas)."
                + (" O PRAZO DE IMPUGNAÇÃO JÁ PASSOU."
                   if prazos["impugnacao_passou"] else ""))

    from ..pecas.minutas import dados_empresa
    empresa = dados_empresa(sessao_db)
    entrada = {
        "ficha_do_portal": {
            "modalidade": lic.modalidade_nome,
            "numero": f"{lic.numero_compra}/{lic.ano_compra}",
            "orgao": lic.orgao_nome, "uf": lic.uf,
            "municipio": lic.municipio_nome,
            "objeto": lic.objeto, "processo": lic.processo,
            "valor_estimado_portal": lic.valor_total_estimado,
            "srp": lic.srp,
            "encerramento_propostas": lic.data_encerramento_proposta,
        },
        "ficha_analisada": dados_ficha,
        "prazos_calculados": prazo_texto,
        "empresa": {"razao_social": empresa.razao_social or "não informado",
                    "cnpj": empresa.cnpj or "não informado"},
        "dossie": _dossie(sessao_db, sessao_data),
        "data_de_hoje": hoje.strftime("%d/%m/%Y"),
    }
    return {"entrada": entrada, "texto_edital": texto_edital,
            "dados_ficha": dados_ficha, "data_sessao": sessao_data}


def gerar_parecer(sessao_db, lic, usuario=None, hoje=None):
    """Gera o parecer rápido (uma chamada). Devolve o Parecer gravado."""
    insumos = montar_insumos(sessao_db, lic, hoje)
    entrada, texto_edital = insumos["entrada"], insumos["texto_edital"]
    mensagem = (json.dumps(entrada, ensure_ascii=False, indent=1)
                + "\n\nBASE JURÍDICA:\n\n" + _base_juridica()
                + "\n\nTEXTO DO EDITAL E ANEXOS:\n\n"
                + (texto_edital[:LIMITE_EDITAL]
                   or "(sem texto legível — análise pela ficha)"))
    texto = cliente.chamar(
        job="parecer_edital",
        prompt_sistema=cliente.carregar_prompt("parecer-edital"),
        mensagem=mensagem, modelo=camadas.PERICIA, max_tokens=16000)
    if "Parecer gerado automaticamente" not in texto[:400]:
        texto = ("> Parecer gerado automaticamente pela plataforma — apoio "
                 "à decisão. Não substitui a leitura do edital nem "
                 "orientação jurídica.\n\n" + texto)
    parecer = Parecer(licitacao_id=lic.id, texto=texto,
                      modelo=camadas.PERICIA,
                      custo_usd=_custo_da_ultima_chamada(),
                      criado_por=getattr(usuario, "id", None))
    sessao_db.add(parecer)
    sessao_db.commit()
    log.info("Parecer gerado para a licitação %s (US$ %.4f)",
             lic.id, parecer.custo_usd)
    return parecer
