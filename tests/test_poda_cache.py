"""Testes do teto do cache de editais — a vacina do volume cheio."""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import ArquivoEdital, Base, Licitacao
from app.editais import arquivos
from app.vigia import checar_disco_cheio


@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


@pytest.fixture()
def cache_falso(tmp_path, monkeypatch, sessao):
    """PASTA_DADOS/editais de mentira com 3 PDFs de 1 MB e idades diferentes."""
    pasta = tmp_path / "editais"
    monkeypatch.setattr(arquivos, "PASTA_DADOS", str(tmp_path))
    monkeypatch.setattr(arquivos, "PASTA_EDITAIS", str(pasta))
    lic = Licitacao(numero_controle_pncp="x", fonte="pncp")
    sessao.add(lic)
    sessao.flush()
    for i, nome in enumerate(["velho", "medio", "novo"]):
        sub = pasta / str(i + 1)
        sub.mkdir(parents=True)
        arquivo = sub / f"{nome}.pdf"
        arquivo.write_bytes(b"x" * 1024 * 1024)
        os.utime(arquivo, (1000 + i * 1000, 1000 + i * 1000))
        sessao.add(ArquivoEdital(
            licitacao_id=lic.id, titulo=nome,
            caminho_local=os.path.relpath(arquivo, tmp_path)))
    sessao.commit()
    return pasta


def test_dentro_do_teto_nao_apaga_nada(sessao, cache_falso):
    apagados, _ = arquivos.podar_cache(sessao, limite_mb=10)
    assert apagados == 0
    assert sessao.query(ArquivoEdital).count() == 3


def test_estouro_apaga_os_mais_antigos_primeiro(sessao, cache_falso):
    apagados, liberados = arquivos.podar_cache(sessao, limite_mb=1)
    assert apagados == 2 and liberados == 2 * 1024 * 1024
    restantes = [a.titulo for a in sessao.query(ArquivoEdital)]
    assert restantes == ["novo"]           # o mais recente sobrevive
    assert not (cache_falso / "1").exists()   # pasta vazia sai junto
    assert (cache_falso / "3" / "novo.pdf").exists()


def test_teto_zero_esvazia_tudo(sessao, cache_falso):
    apagados, _ = arquivos.podar_cache(sessao, limite_mb=0)
    assert apagados == 3
    assert sessao.query(ArquivoEdital).count() == 0


def test_cache_inexistente_nao_quebra(sessao, tmp_path, monkeypatch):
    monkeypatch.setattr(arquivos, "PASTA_EDITAIS",
                        str(tmp_path / "nao-existe"))
    assert arquivos.podar_cache(sessao, limite_mb=1) == (0, 0)


def test_linha_orfa_nao_bloqueia_novo_download(sessao, cache_falso,
                                               monkeypatch):
    """A causa do bug de Bacabeira: linha no banco cujo arquivo saiu do
    disco fazia o download ser pulado para sempre ('url já baixada')."""
    lic = sessao.query(Licitacao).first()
    lic.orgao_cnpj, lic.ano_compra = "00000000000000", 2026
    lic.numero_controle_pncp = "00000000000000-1-000001/2026"
    vitima = sessao.query(ArquivoEdital).filter_by(titulo="velho").first()
    vitima.url_origem = "https://pncp.gov.br/doc/1"
    sessao.commit()
    os.remove(os.path.join(str(cache_falso.parent), vitima.caminho_local))

    listadas = []
    monkeypatch.setattr(arquivos, "listar_arquivos_compra",
                        lambda *a, **k: listadas.append(1) or [])
    arquivos.baixar_arquivos(sessao, lic)
    # A linha órfã sumiu do banco — na próxima listagem com documentos, a
    # url volta a ser baixada em vez de cair no "já baixado".
    assert listadas
    titulos = [a.titulo for a in sessao.query(ArquivoEdital)]
    assert "velho" not in titulos and len(titulos) == 2


# ----------------------------------------------------------- vigia de disco
def test_disco_com_folga_nao_e_problema():
    assert checar_disco_cheio(5000) is None
    assert checar_disco_cheio(None) is None    # não conseguiu medir: silêncio


def test_disco_no_limite_avisa():
    p = checar_disco_cheio(120)
    assert p and p["chave"] == "disco_cheio" and "120 MB" in p["titulo"]


# ------------------------------------------- extensão e tipo para download
def test_para_download_fareja_pdf_sem_extensao(tmp_path):
    """PNCP manda octet-stream sem extensão: o download chegava ilegível
    no Windows do usuário ('tive que escolher o Adobe para abrir')."""
    caminho = tmp_path / "1-Edital_PE_39_2026"
    caminho.write_bytes(b"%PDF-1.7 conteudo")
    nome, media = arquivos.para_download(str(caminho))
    assert nome == "1-Edital_PE_39_2026.pdf" and media == "application/pdf"


def test_para_download_respeita_extensao_existente(tmp_path):
    caminho = tmp_path / "2-Planilha.xlsx"
    caminho.write_bytes(b"PK\x03\x04zipzip")
    nome, media = arquivos.para_download(str(caminho))
    assert nome == "2-Planilha.xlsx"
    assert "spreadsheet" in media


def test_extensao_do_conteudo():
    assert arquivos.extensao_do_conteudo(b"%PDF-1.4") == ".pdf"
    assert arquivos.extensao_do_conteudo(b"PK\x03\x04") == ".zip"
    assert arquivos.extensao_do_conteudo(b"Rar!\x1a") == ".rar"
    assert arquivos.extensao_do_conteudo(b"???") == ""
