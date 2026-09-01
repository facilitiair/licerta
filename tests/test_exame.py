"""Exame técnico por código: hash, formato real, revisões e códigos."""
from app.analista import exame


def test_examina_pdf_de_verdade(tmp_path, monkeypatch):
    from pypdf import PdfWriter
    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    caminho = tmp_path / "doc.pdf"
    with open(caminho, "wb") as f:
        escritor.write(f)
    monkeypatch.setattr(exame, "PASTA_DADOS", str(tmp_path))
    resultado = exame.examinar_pdf(
        "doc.pdf", texto="Código de controle: 265.646/26-96")
    assert resultado["formato_real"] == "PDF"
    assert len(resultado["sha256"]) == 64
    assert resultado["revisoes_do_pdf"] >= 1
    assert resultado["paginas"] == 1
    assert resultado["tem_assinatura_digital"] is False
    assert resultado["codigos_de_autenticidade"] == ["265.646/26-96"]


def test_arquivo_inexistente_devolve_none(monkeypatch, tmp_path):
    monkeypatch.setattr(exame, "PASTA_DADOS", str(tmp_path))
    assert exame.examinar_pdf("nao-existe.pdf") is None
    assert exame.examinar_pdf(None) is None


def test_formato_real_nao_confia_na_extensao(tmp_path, monkeypatch):
    caminho = tmp_path / "finge-ser.pdf"
    caminho.write_bytes(b"PK\x03\x04conteudozip")
    monkeypatch.setattr(exame, "PASTA_DADOS", str(tmp_path))
    resultado = exame.examinar_pdf("finge-ser.pdf")
    assert resultado["formato_real"] == "ZIP/OOXML"
    assert resultado["extensao_declarada"] == ".pdf"
