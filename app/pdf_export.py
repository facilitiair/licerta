"""Exporta texto em markdown (ficha, parecer, minuta, laudo) para PDF.

Mesmo markdown que vira Word em docx_export: aqui ele vira HTML simples e
o PyMuPDF (já presente para o OCR) o pagina num PDF A4. Sem dependência
de sistema, sem serviço externo — o arquivo nasce no servidor e desce
pronto para anexar, imprimir ou encaminhar.
"""
import html
import io
import re

MEDIA_PDF = "application/pdf"

_CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; }
h1 { font-size: 17pt; margin: 0 0 8pt 0; }
h2 { font-size: 13.5pt; margin: 14pt 0 4pt 0; }
h3 { font-size: 11.5pt; margin: 10pt 0 3pt 0; }
h4 { font-size: 10.5pt; margin: 8pt 0 2pt 0; }
p { margin: 0 0 6pt 0; }
li { margin: 0 0 2pt 0; }
blockquote { margin: 6pt 0; padding: 4pt 8pt; border-left: 3pt solid #999;
             color: #333; }
table { border-collapse: collapse; margin: 6pt 0; }
td, th { border: 0.5pt solid #888; padding: 2pt 5pt; font-size: 9.5pt;
         vertical-align: top; }
.rodape { color: #666; font-size: 8.5pt; margin-top: 14pt; }
"""

_INLINE = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*|`[^`]+?`)")


def _inline(texto):
    partes = []
    for parte in _INLINE.split(texto):
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**"):
            partes.append("<b>" + html.escape(parte[2:-2]) + "</b>")
        elif parte.startswith("*") and parte.endswith("*") and len(parte) > 2:
            partes.append("<i>" + html.escape(parte[1:-1]) + "</i>")
        elif parte.startswith("`") and parte.endswith("`"):
            partes.append("<code>" + html.escape(parte[1:-1]) + "</code>")
        else:
            partes.append(html.escape(parte))
    return "".join(partes)


def _e_linha_de_tabela(linha):
    return linha.startswith("|") and linha.rstrip().endswith("|")


def markdown_para_html(texto, titulo=None, rodape=None):
    """HTML autocontido a partir do markdown que os prompts produzem."""
    saida = []
    if titulo:
        saida.append(f"<h1>{html.escape(titulo)}</h1>")
    linhas = (texto or "").splitlines()
    i, lista_aberta = 0, None
    while i < len(linhas):
        crua = linhas[i].strip()
        e_item = re.match(r"^[-*+]\s+", crua)
        e_numero = re.match(r"^\d+[.)]\s+", crua)
        tipo_lista = "ul" if e_item else "ol" if e_numero else None
        if lista_aberta and tipo_lista != lista_aberta:
            saida.append(f"</{lista_aberta}>")
            lista_aberta = None
        if not crua:
            i += 1
            continue
        if tipo_lista:
            if not lista_aberta:
                saida.append(f"<{tipo_lista}>")
                lista_aberta = tipo_lista
            item = re.sub(r"^([-*+]|\d+[.)])\s+", "", crua)
            saida.append(f"<li>{_inline(item)}</li>")
        elif crua.startswith("#"):
            nivel = min(len(crua) - len(crua.lstrip("#")), 4)
            saida.append(f"<h{nivel}>{_inline(crua.lstrip('#').strip())}"
                         f"</h{nivel}>")
        elif crua.startswith(">"):
            saida.append("<blockquote>"
                         + _inline(crua.lstrip("> ").strip()) + "</blockquote>")
        elif crua in ("---", "***", "___"):
            saida.append("<hr>")
        elif _e_linha_de_tabela(crua):
            saida.append("<table>")
            while i < len(linhas) and _e_linha_de_tabela(linhas[i].strip()):
                celulas = [c.strip() for c in
                           linhas[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in celulas):
                    saida.append("<tr>" + "".join(
                        f"<td>{_inline(c)}</td>" for c in celulas) + "</tr>")
                i += 1
            saida.append("</table>")
            continue
        else:
            saida.append(f"<p>{_inline(crua)}</p>")
        i += 1
    if lista_aberta:
        saida.append(f"</{lista_aberta}>")
    if rodape:
        saida.append(f'<p class="rodape">{html.escape(rodape)}</p>')
    return "<html><body>" + "\n".join(saida) + "</body></html>"


def markdown_para_pdf(texto, titulo=None, rodape=None):
    """Bytes de um PDF A4 com o markdown paginado."""
    import pymupdf
    story = pymupdf.Story(html=markdown_para_html(texto, titulo, rodape),
                          user_css=_CSS)
    buffer = io.BytesIO()
    escritor = pymupdf.DocumentWriter(buffer)
    folha = pymupdf.paper_rect("a4")
    area = folha + (42, 42, -42, -48)
    mais = True
    while mais:
        dispositivo = escritor.begin_page(folha)
        mais, _ = story.place(area)
        story.draw(dispositivo)
        escritor.end_page()
    escritor.close()
    return buffer.getvalue()
