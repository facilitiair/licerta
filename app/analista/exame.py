"""Exame técnico de arquivos por CÓDIGO — a camada determinística do
perito forense digital, portada para o servidor.

O gabinete pericial original roda exiftool/qpdf numa bancada local; aqui
extraímos o que dá para extrair com Python puro, sem executar conteúdo:
hash SHA-256, formato real pelos primeiros bytes, contagem de revisões
do PDF (atualizações incrementais), metadados e sua coerência interna,
presença de assinatura digital, anexos embutidos e conteúdo ativo.

Tudo aqui é ACHADO TÉCNICO BRUTO para os peritos de linguagem — o código
mede, o laudo interpreta. Nenhum item isolado prova nada: atualização
incremental, por exemplo, é o comportamento normal de um PDF assinado.
"""
import hashlib
import logging
import os
import re

from ..config import PASTA_DADOS

log = logging.getLogger("radar.analista")

_MAGIAS = ((b"%PDF", "PDF"), (b"PK\x03\x04", "ZIP/OOXML"),
           (b"Rar!", "RAR"), (b"\xd0\xcf\x11\xe0", "OLE (doc/xls antigo)"),
           (b"\x89PNG", "PNG"), (b"\xff\xd8\xff", "JPEG"))

# Códigos de autenticidade que os portais brasileiros estampam nos
# documentos — extraídos para o quesito D0 (conferência na fonte).
_PADRAO_CODIGO = re.compile(
    r"(?:c[óo]digo\s+(?:de\s+)?(?:controle|autentica[çc][ãa]o|verifica[çc]"
    r"[ãa]o|validador)|chave\s+de\s+acesso)[:\s]*([A-Z0-9][A-Z0-9 ./-]{4,60})",
    re.IGNORECASE)


def _formato_real(inicio):
    for magia, nome in _MAGIAS:
        if inicio.startswith(magia):
            return nome
    return "desconhecido"


def examinar_pdf(caminho_relativo, texto=None):
    """Exame estático de um arquivo. Devolve dict de achados brutos
    (ou None se o arquivo não existe)."""
    caminho = os.path.join(PASTA_DADOS, caminho_relativo or "")
    if not (caminho_relativo and os.path.exists(caminho)):
        return None
    try:
        with open(caminho, "rb") as f:
            bruto = f.read()
    except OSError:
        return None
    exame = {
        "sha256": hashlib.sha256(bruto).hexdigest(),
        "tamanho_bytes": len(bruto),
        "formato_real": _formato_real(bruto[:8]),
        "extensao_declarada": os.path.splitext(caminho)[1].lower() or "(sem)",
    }
    if exame["formato_real"] == "PDF":
        # revisões: cada gravação incremental acrescenta um %%EOF
        exame["revisoes_do_pdf"] = bruto.count(b"%%EOF")
        exame["tem_assinatura_digital"] = b"/ByteRange" in bruto \
            and (b"/Sig" in bruto or b"adbe.pkcs7" in bruto
                 or b"ETSI.CAdES" in bruto)
        exame["tem_anexos_embutidos"] = b"/EmbeddedFile" in bruto
        exame["tem_javascript"] = b"/JavaScript" in bruto or b"/JS" in bruto
        try:
            import io

            from pypdf import PdfReader
            leitor = PdfReader(io.BytesIO(bruto))
            exame["paginas"] = len(leitor.pages)
            meta = leitor.metadata or {}
            exame["metadados"] = {
                "produtor": str(meta.get("/Producer", "") or ""),
                "criador": str(meta.get("/Creator", "") or ""),
                "criacao": str(meta.get("/CreationDate", "") or ""),
                "modificacao": str(meta.get("/ModDate", "") or ""),
            }
            cri, mod = exame["metadados"]["criacao"], \
                exame["metadados"]["modificacao"]
            if cri and mod and mod < cri:
                exame["alerta_datas"] = ("data de modificação anterior à "
                                        "de criação — verificar")
        except Exception:  # noqa: BLE001 — PDF hostil não derruba o exame
            exame["erro_leitura"] = "pypdf não conseguiu abrir (estrutura?)"
    if texto:
        codigos = [c.strip() for c in _PADRAO_CODIGO.findall(texto)]
        if codigos:
            exame["codigos_de_autenticidade"] = codigos[:5]
    return exame


def examinar_dossie(sessao_db, itens_dossie):
    """Exame técnico de cada documento do dossiê que tem arquivo.

    `itens_dossie` é a lista que `parecer._dossie` monta (nome/tipo/
    texto). Casa cada item com o DocumentoEmpresa pelo nome para achar o
    arquivo no disco. Devolve {nome: exame}."""
    from ..db import DocumentoEmpresa
    docs = {d.nome: d for d in sessao_db.query(DocumentoEmpresa)
            .filter_by(arquivado=False)}
    exames = {}
    for item in itens_dossie:
        doc = docs.get(item["nome"])
        if not doc:
            continue
        exame = examinar_pdf(doc.caminho_local,
                             texto=item.get("texto_extraido"))
        if exame:
            exames[item["nome"]] = exame
    return exames
