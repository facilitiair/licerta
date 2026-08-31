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


# ----------------------------------------------------------- vigia de disco
def test_disco_com_folga_nao_e_problema():
    assert checar_disco_cheio(5000) is None
    assert checar_disco_cheio(None) is None    # não conseguiu medir: silêncio


def test_disco_no_limite_avisa():
    p = checar_disco_cheio(120)
    assert p and p["chave"] == "disco_cheio" and "120 MB" in p["titulo"]
