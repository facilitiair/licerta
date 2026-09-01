"""Exportação de markdown para Word: títulos, listas, tabela e inline."""
import io
import zipfile

from app.docx_export import markdown_para_docx

EXEMPLO = """# Parecer — Pregão 7/2026

> Aviso de apoio à decisão.

## 1. Em uma frase

Vale **participar**, com *uma* ressalva.

- CND Federal ok
- CREA vence antes da sessão

| Documento | Situação |
|---|---|
| FGTS | válido |
| CNDT | válido |

1. Renovar o CREA
2. Enviar proposta
"""


def _texto_do_docx(conteudo):
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        return z.read("word/document.xml").decode("utf-8")


def test_gera_docx_valido_com_estrutura():
    conteudo = markdown_para_docx(EXEMPLO, titulo="Parecer do analista")
    xml = _texto_do_docx(conteudo)
    for trecho in ("Parecer do analista", "Em uma frase", "participar",
                   "CND Federal ok", "FGTS", "Renovar o CREA"):
        assert trecho in xml, trecho
    # o marcador de markdown não pode vazar para o Word
    assert "**" not in xml and "|---|" not in xml


def test_texto_vazio_nao_quebra():
    conteudo = markdown_para_docx("")
    assert _texto_do_docx(conteudo)  # docx válido mesmo vazio
