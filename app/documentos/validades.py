"""Vigia de validades do dossiê (arquitetura §5, módulo Documentos).

Tudo aqui é código determinístico sobre datas — nunca IA (princípio 2:
um alerta de prazo errado encerra a confiança do cliente). A única ajuda
"esperta" é a SUGESTÃO de validade lida do PDF por expressão regular, e
mesmo essa passa pela confirmação do usuário na tela.
"""
import logging
import os
import re
from datetime import date, datetime, timedelta

from ..config import PASTA_DADOS, config, hoje as hoje_local
from ..db import DocumentoEmpresa, Sessao

log = logging.getLogger("radar.documentos")

# Marcos de aviso, em dias antes do vencimento. -1 = já venceu (avisa 1×).
MARCOS = (30, 15, 7, 3, 1, 0)

TIPOS = ["CND Federal (RFB/PGFN)", "CRF do FGTS", "CNDT Trabalhista",
         "CND Estadual", "CND Municipal", "Certidão de Falência",
         "Contrato Social", "Balanço Patrimonial", "Atestado de Capacidade",
         "CAT", "Registro CREA/CAU", "Alvará", "Procuração", "Outro"]


def _data_iso(texto):
    try:
        return datetime.strptime((texto or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def dias_para_vencer(doc, hoje=None):
    """Dias até o vencimento (negativo = vencido); None = sem validade."""
    validade = _data_iso(doc.validade)
    if not validade:
        return None
    return (validade - (hoje or hoje_local())).days


def situacao_documento(doc, hoje=None):
    """('vencido'|'vencendo'|'vigente'|'sem_validade', dias) para a tela."""
    dias = dias_para_vencer(doc, hoje)
    if dias is None:
        return "sem_validade", None
    if dias < 0:
        return "vencido", dias
    if dias <= 30:
        return "vencendo", dias
    return "vigente", dias


def marco_devido(doc, hoje=None):
    """Qual marco de aviso está devido AGORA (ou None).

    Cruzou um marco ainda não avisado → devolve o marco. O marco corrente é
    o MENOR dos marcos ≥ dias restantes: com 14 dias restantes o marco é 15;
    vencido é o marco -1. Avisar uma vez por marco segura a fadiga: seis
    avisos no total por documento, do primeiro ao vencimento.
    """
    dias = dias_para_vencer(doc, hoje)
    if dias is None or getattr(doc, "arquivado", False):
        return None
    marco = -1 if dias < 0 else min((m for m in MARCOS if m >= dias),
                                    default=None)
    if marco is None:                      # ainda longe do primeiro marco
        return None
    ultimo = getattr(doc, "ultimo_aviso_dias", None)
    if ultimo is not None and ultimo <= marco:
        return None                        # este marco (ou um mais urgente) já saiu
    return marco


def _frase(doc, marco, dias):
    validade = _data_iso(doc.validade)
    data = validade.strftime("%d/%m/%Y") if validade else "?"
    if marco == -1:
        atraso = -dias
        return (f"🟥 VENCIDO há {atraso} dia{'s' if atraso != 1 else ''}: "
                f"{doc.nome} ({doc.tipo}) — venceu em {data}")
    if dias == 0:
        return f"🟧 VENCE HOJE: {doc.nome} ({doc.tipo}) — {data}"
    return (f"⏳ Vence em {dias} dia{'s' if dias != 1 else ''}: "
            f"{doc.nome} ({doc.tipo}) — {data}")


def avisar_vencimentos(sessao_db=None, hoje=None, host=None):
    """Varre o dossiê e avisa os administradores dos marcos cruzados.

    Devolve quantos documentos entraram no aviso. Como nos alertas, o marco
    só é gravado se algum canal aceitou a mensagem — canal fora do ar
    tenta de novo no próximo ciclo.
    """
    from ..vigia import avisar_admins
    hoje = hoje or hoje_local()
    sessao = sessao_db or Sessao()
    try:
        docs = (sessao.query(DocumentoEmpresa)
                .filter_by(arquivado=False)
                .filter(DocumentoEmpresa.validade.isnot(None)).all())
        devidos = []
        for doc in docs:
            marco = marco_devido(doc, hoje)
            if marco is not None:
                devidos.append((doc, marco, dias_para_vencer(doc, hoje)))
        if not devidos:
            return 0
        devidos.sort(key=lambda t: t[2])   # o mais urgente primeiro
        linhas = ["📄 Licerta — validades do dossiê da empresa\n"]
        linhas += [_frase(doc, marco, dias) for doc, marco, dias in devidos]
        linhas.append(f"\nRenovar e atualizar: "
                      f"{(host or config.APP_URL)}/documentos")
        if avisar_admins(sessao, "\n".join(linhas), resumo=_frase(*devidos[0])):
            for doc, marco, _ in devidos:
                doc.ultimo_aviso_dias = marco
            sessao.commit()
        return len(devidos)
    except Exception:  # noqa: BLE001 — vigia de validade nunca derruba nada
        sessao.rollback()
        log.exception("Erro no aviso de validades")
        return 0
    finally:
        if sessao_db is None:
            sessao.close()


_VAL_NO_NOME = re.compile(
    r"VAL[.\s]*([0-3]?\d)[-/.]([01]?\d)[-/.](\d{4})", re.IGNORECASE)


def validade_do_nome(nome_arquivo):
    """Validade embutida no NOME do arquivo ('CND VAL.30-08-2026.pdf').

    Quem organiza dossiê costuma carimbar a validade no nome — é a fonte
    mais barata que existe, e o upload em lote a aproveita antes de abrir
    o PDF.
    """
    m = _VAL_NO_NOME.search(nome_arquivo or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)),
                    int(m.group(1))).isoformat()
    except ValueError:
        return None


def nome_amigavel(nome_arquivo):
    """'02 - FGTS VAL.24-08-2026.pdf' → 'FGTS' — o rótulo que a lista mostra."""
    base = os.path.splitext(os.path.basename(nome_arquivo or ""))[0]
    base = re.sub(r"^\s*\d+\s*[-–.]\s*", "", base)      # prefixo numérico
    base = _VAL_NO_NOME.sub("", base)                    # carimbo de validade
    base = re.sub(r"[_]+", " ", base)
    base = re.sub(r"\s{2,}", " ", base).strip(" -–.")
    return base[:120] or "Documento"


# ------------------------------------------------ sugestão de validade (regex)
_MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
          "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
          "outubro": 10, "novembro": 11, "dezembro": 12}

_PADRAO_DATA = re.compile(
    r"(?:v[áa]lid[ao][^.\n]{0,40}?|validade[^.\n]{0,40}?|vencimento[^.\n]{0,40}?)"
    r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
    re.IGNORECASE)


def _para_iso(bruto):
    bruto = bruto.strip()
    try:
        if "/" in bruto:
            return datetime.strptime(bruto, "%d/%m/%Y").date().isoformat()
        if "-" in bruto:
            return datetime.strptime(bruto, "%Y-%m-%d").date().isoformat()
        dia, _, mes, _, ano = bruto.lower().split()
        return date(int(ano), _MESES[mes], int(dia)).isoformat()
    except (ValueError, KeyError):
        return None


def texto_do_pdf(caminho_relativo):
    """Texto das primeiras páginas de um PDF do dossiê ('' se não der)."""
    caminho = os.path.join(PASTA_DADOS, caminho_relativo or "")
    if not (caminho_relativo and caminho.lower().endswith(".pdf")
            and os.path.exists(caminho)):
        return ""
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "")
                         for p in PdfReader(caminho).pages[:5])
    except Exception:  # noqa: BLE001 — sugestão é cortesia
        return ""


def sugerir_validade(caminho_relativo, hoje=None):
    """Tenta ler a validade de um PDF de certidão — SUGESTÃO, nunca decisão.

    Procura "válida até / validade / vencimento" seguido de data nas
    primeiras páginas. Datas no passado distante ou absurdas no futuro são
    descartadas (é mais provável ser a data de emissão ou um artigo de lei).
    """
    texto = texto_do_pdf(caminho_relativo)
    if not texto:
        return None
    hoje = hoje or hoje_local()
    candidatas = []
    for bruto in _PADRAO_DATA.findall(texto):
        iso = _para_iso(bruto)
        if not iso:
            continue
        data = _data_iso(iso)
        if hoje - timedelta(days=30) <= data <= hoje + timedelta(days=730):
            candidatas.append(iso)
    return max(candidatas) if candidatas else None
