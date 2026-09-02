"""OCR por visão: PDF digitalizado (só imagem) vira texto e entra no mesmo
fluxo do texto nativo — ficha, dossiê, perícia. Com cache e custo logado."""
import pymupdf
import pytest

from ia import ocr


def pdf_escaneado(caminho, paginas=1, texto="CERTIDÃO NEGATIVA"):
    """PDF cujas páginas são IMAGENS de texto — sem camada de texto."""
    origem = pymupdf.open()
    for i in range(paginas):
        pg = origem.new_page(width=595, height=842)
        pg.insert_text((72, 100), f"{texto} {i + 1}", fontsize=24)
    doc = pymupdf.open()
    for pg in origem:
        pix = pg.get_pixmap(dpi=100)
        nova = doc.new_page(width=595, height=842)
        nova.insert_image(nova.rect, pixmap=pix)
    doc.save(str(caminho))
    doc.close()
    origem.close()


def pdf_com_texto(caminho, texto):
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((72, 100), texto, fontsize=12)
    doc.save(str(caminho))
    doc.close()


@pytest.fixture()
def visao_falsa(monkeypatch):
    """Dublê do modelo de visão: devolve um marcador por imagem recebida."""
    chamadas = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")

    def falso(job, prompt_sistema, imagens, mensagem, modelo=None, **k):
        chamadas.append({"job": job, "n": len(imagens), "modelo": modelo})
        numeros = [int(x) for x in mensagem.split("página ")[1:]
                   for x in [x.split(",")[0].rstrip(".")]]
        return "\n".join(f"=== PÁGINA {n} ===\nTexto lido da página {n}."
                         for n in numeros)
    monkeypatch.setattr(ocr.cliente, "chamar_visao", falso)
    return chamadas


def test_pdf_escaneado_nao_tem_camada_de_texto(tmp_path):
    caminho = tmp_path / "scan.pdf"
    pdf_escaneado(caminho)
    from pypdf import PdfReader
    nativo = "".join(p.extract_text() or "" for p in PdfReader(str(caminho)).pages)
    assert ocr.pdf_precisa_de_ocr(nativo)


def test_transcreve_em_lotes_paralelos_e_guarda_cache(tmp_path, visao_falsa):
    caminho = tmp_path / "edital.pdf"
    pdf_escaneado(caminho, paginas=9)
    texto = ocr.transcrever_pdf(str(caminho), job="ocr_teste")
    assert "=== PÁGINA 1 ===" in texto and "=== PÁGINA 9 ===" in texto
    assert texto.index("PÁGINA 2") < texto.index("PÁGINA 9")   # em ordem
    assert sum(c["n"] for c in visao_falsa) == 9
    assert len(visao_falsa) == 3           # lotes de 4: 4 + 4 + 1
    assert all(c["job"] == "ocr_teste" for c in visao_falsa)
    assert (tmp_path / "edital.pdf.ocr.txt").exists()
    # segunda leitura: cache, zero chamadas
    ocr.transcrever_pdf(str(caminho), job="ocr_teste")
    assert len(visao_falsa) == 3


def test_texto_do_pdf_usa_nativo_quando_existe(tmp_path, visao_falsa):
    caminho = tmp_path / "nativo.pdf"
    pdf_com_texto(caminho, "Texto nativo suficiente. " * 20)
    texto, veio_de_ocr = ocr.texto_do_pdf(str(caminho))
    assert not veio_de_ocr and "Texto nativo" in texto
    assert visao_falsa == []


def test_sem_chave_de_ia_ocr_devolve_vazio_sem_erro(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    caminho = tmp_path / "scan.pdf"
    pdf_escaneado(caminho)
    assert ocr.transcrever_pdf(str(caminho)) == ""


def test_resposta_sem_marcador_nao_se_perde():
    assert ocr._separar_paginas("texto solto", [7, 8]) == {7: "texto solto"}


def test_edital_escaneado_entra_na_ficha(tmp_path, visao_falsa, monkeypatch):
    """extrair_texto_pdfs desistia do PDF só-imagem; agora lê por visão."""
    from app.editais import analise
    monkeypatch.setattr(analise, "PASTA_DADOS", str(tmp_path))
    pdf_escaneado(tmp_path / "edital.pdf", paginas=2)

    class Arq:
        caminho_local, titulo, tipo = "edital.pdf", "Edital", "edital"
    texto, lidos = analise.extrair_texto_pdfs([Arq()])
    assert lidos and "Texto lido da página 2" in texto
    assert visao_falsa[0]["job"] == "ocr_edital"


def test_certidao_escaneada_no_dossie_le_so_a_capa(tmp_path, visao_falsa,
                                                    monkeypatch):
    from app.documentos import validades
    monkeypatch.setattr(validades, "PASTA_DADOS", str(tmp_path))
    pdf_escaneado(tmp_path / "cnd.pdf", paginas=6)
    texto = validades.texto_do_pdf("cnd.pdf")
    assert "Texto lido da página 1" in texto
    assert sum(c["n"] for c in visao_falsa) == 2      # só as 2 primeiras
    assert visao_falsa[0]["job"] == "ocr_dossie"


def test_chamada_de_visao_monta_o_pedido_da_api(monkeypatch):
    from ia import cliente
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-teste")
    capturado = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"content": [{"type": "text", "text": "=== PÁGINA 1 ===\nok"}],
                    "usage": {"input_tokens": 10, "output_tokens": 5}}
    monkeypatch.setattr(cliente.requests, "post",
                        lambda url, **k: capturado.update(k) or Resp())
    monkeypatch.setattr(cliente, "_registrar_custo", lambda *a, **k: None)
    texto = cliente.chamar_visao("ocr_teste", "sistema", [b"\xff\xd8jpg"],
                                 "leia", modelo="claude-sonnet-5")
    assert texto.startswith("=== PÁGINA 1 ===")
    corpo = capturado["json"]
    blocos = corpo["messages"][0]["content"]
    assert blocos[0]["type"] == "image"
    assert blocos[0]["source"]["media_type"] == "image/jpeg"
    assert blocos[-1] == {"type": "text", "text": "leia"}
    assert corpo["model"] == "claude-sonnet-5"


# ------------------------------------------- análise longa em segundo plano
def test_precisa_de_ocr_so_para_digitalizado_sem_cache(tmp_path, monkeypatch):
    from app.editais import analise
    monkeypatch.setattr(analise, "PASTA_DADOS", str(tmp_path))
    pdf_escaneado(tmp_path / "scan.pdf")
    pdf_com_texto(tmp_path / "texto.pdf", "Edital com texto nativo. " * 30)

    class Arq:
        def __init__(self, nome):
            self.caminho_local = nome
    assert analise.precisa_de_ocr([Arq("scan.pdf")])
    assert not analise.precisa_de_ocr([Arq("texto.pdf")])
    (tmp_path / "scan.pdf.ocr.txt").write_text("já lido", encoding="utf-8")
    assert not analise.precisa_de_ocr([Arq("scan.pdf")])


def test_analise_em_fundo_roda_uma_vez_e_libera(monkeypatch):
    import threading
    from app.editais import analise
    feito = threading.Event()
    monkeypatch.setattr(analise, "analisar_edital",
                        lambda s, lic, forcar=False: feito.set())
    assert analise.iniciar_em_fundo(999999)     # licitação inexistente: só
    assert not analise.iniciar_em_fundo(999999)  # uma por vez
    for _ in range(50):
        if not analise.em_andamento(999999):
            break
        threading.Event().wait(0.1)
    assert not analise.em_andamento(999999)


def test_rota_da_ficha_responde_enquanto_analisa():
    from fastapi.testclient import TestClient
    from app.config import config
    from app.db import Licitacao, Sessao
    from app.main import app
    s = Sessao()
    try:
        lic = s.query(Licitacao).first()
        lic_id = lic.id if lic else None
    finally:
        s.close()
    if not lic_id:
        pytest.skip("banco local sem licitação")
    with TestClient(app) as c:
        c.post("/login", data={"email": "", "senha": config.APP_SENHA},
               follow_redirects=False)
        assert c.get(f"/licitacoes/{lic_id}/ficha").status_code == 200
        assert c.get("/licitacoes/999999/ficha").status_code == 404
