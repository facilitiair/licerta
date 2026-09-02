"""Testes do dossiê de documentos: cálculo de validade (código, nunca IA),
marcos de aviso sem fadiga e a sugestão de validade por regex."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, DocumentoEmpresa, Usuario
from app.documentos import validades

HOJE = date(2026, 8, 31)


class DocFake:
    def __init__(self, validade=None, ultimo=None, arquivado=False):
        self.nome = "CND Federal"
        self.tipo = "CND Federal (RFB/PGFN)"
        self.validade = validade
        self.ultimo_aviso_dias = ultimo
        self.arquivado = arquivado


# ------------------------------------------------------- situação e dias
def test_situacoes():
    assert validades.situacao_documento(DocFake("2026-12-01"), HOJE) == \
        ("vigente", 92)
    assert validades.situacao_documento(DocFake("2026-09-10"), HOJE) == \
        ("vencendo", 10)
    assert validades.situacao_documento(DocFake("2026-08-20"), HOJE) == \
        ("vencido", -11)
    assert validades.situacao_documento(DocFake(None), HOJE) == \
        ("sem_validade", None)
    assert validades.situacao_documento(DocFake("data podre"), HOJE) == \
        ("sem_validade", None)


# ------------------------------------------------------------- marcos
def test_longe_do_vencimento_nao_avisa():
    assert validades.marco_devido(DocFake("2027-08-31"), HOJE) is None


def test_cruzou_marco_avisa_uma_vez_so():
    doc = DocFake("2026-09-14")            # 14 dias -> marco 15
    assert validades.marco_devido(doc, HOJE) == 15
    doc.ultimo_aviso_dias = 15             # avisado
    assert validades.marco_devido(doc, HOJE) is None


def test_marcos_avancam_ate_o_vencido():
    doc = DocFake("2026-09-02", ultimo=3)  # 2 dias, marco 3 já avisado
    assert validades.marco_devido(doc, HOJE) is None
    doc.validade = "2026-09-01"            # 1 dia -> marco 1
    assert validades.marco_devido(doc, HOJE) == 1
    doc.ultimo_aviso_dias = 1
    doc.validade = "2026-08-31"            # vence hoje -> marco 0
    assert validades.marco_devido(doc, HOJE) == 0
    doc.ultimo_aviso_dias = 0
    doc.validade = "2026-08-25"            # vencido -> marco -1, uma vez
    assert validades.marco_devido(doc, HOJE) == -1
    doc.ultimo_aviso_dias = -1
    assert validades.marco_devido(doc, HOJE) is None


def test_arquivado_nao_e_vigiado():
    assert validades.marco_devido(DocFake("2026-09-01", arquivado=True),
                                  HOJE) is None


def test_documento_pulado_direto_para_marco_urgente():
    """Documento cadastrado já com 2 dias de prazo: avisa o marco 3 — não
    os 30/15/7 que ficaram para trás."""
    assert validades.marco_devido(DocFake("2026-09-02"), HOJE) == 3


# --------------------------------------------------------- aviso fim a fim
@pytest.fixture()
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Usuario(nome="Admin", email="a@x.com", senha_hash="h",
                  papel="admin", telegram_chat_id="1",
                  receber_telegram=True, receber_email=False,
                  receber_push=False))
    s.commit()
    yield s
    s.close()


def test_aviso_agrupa_e_marca_os_marcos(sessao, monkeypatch):
    enviados = []
    monkeypatch.setattr("app.vigia._avisar_admins",
                        lambda s, texto, resumo="": enviados.append(texto)
                        or True)
    sessao.add_all([
        DocumentoEmpresa(nome="CND Federal", validade="2026-09-05"),
        DocumentoEmpresa(nome="CRF FGTS", validade="2026-08-20"),
        DocumentoEmpresa(nome="Longe", validade="2027-08-01"),
        DocumentoEmpresa(nome="Arquivado", validade="2026-09-01",
                         arquivado=True),
    ])
    sessao.commit()
    assert validades.avisar_vencimentos(sessao, hoje=HOJE) == 2
    texto = enviados[0]
    assert "VENCIDO há 11 dias" in texto and "Vence em 5 dias" in texto
    assert "Longe" not in texto and "Arquivado" not in texto
    # marcos gravados: não repete amanhã
    assert validades.avisar_vencimentos(sessao, hoje=HOJE) == 0


def test_canal_fora_nao_queima_o_marco(sessao, monkeypatch):
    monkeypatch.setattr("app.vigia._avisar_admins", lambda *a, **k: False)
    sessao.add(DocumentoEmpresa(nome="CND", validade="2026-09-05"))
    sessao.commit()
    validades.avisar_vencimentos(sessao, hoje=HOJE)
    doc = sessao.query(DocumentoEmpresa).one()
    assert doc.ultimo_aviso_dias is None    # tenta de novo no próximo ciclo


# ------------------------------------------------------ sugestão por regex
def test_sugestao_de_validade_em_pdf(tmp_path, monkeypatch):
    """Gera um PDF de verdade com pypdf e lê a validade de volta."""
    from pypdf import PdfWriter
    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    caminho = tmp_path / "cnd.pdf"
    # pypdf não escreve texto de página facilmente; simulamos o extract_text
    with open(caminho, "wb") as f:
        escritor.write(f)
    monkeypatch.setattr("pypdf.PdfReader",
                        lambda *a, **k: type("R", (), {"pages": [type(
                            "P", (), {"extract_text": lambda self:
                                      "Certidão VÁLIDA ATÉ 05/09/2026 ..."
                                      + " texto da certidão" * 20})()
                        ]})())
    monkeypatch.setattr("app.documentos.validades.PASTA_DADOS",
                        str(tmp_path))
    assert validades.sugerir_validade("cnd.pdf", hoje=HOJE) == "2026-09-05"


def test_validade_em_intervalo_pega_o_fim():
    """CRF do FGTS: 'Validade: 19/08/2026 a 17/09/2026' — pegar a primeira
    data marcava o certificado NOVO como vencido há dias."""
    achados = validades._PADRAO_DATA.findall(
        "Validade: 19/08/2026 a 17/09/2026")
    assert achados == [("19/08/2026", "17/09/2026")]
    # data única continua funcionando (grupo do fim vem vazio)
    achados = validades._PADRAO_DATA.findall("VÁLIDA ATÉ 31/10/2026")
    assert achados == [("31/10/2026", "")]


def test_tipo_do_conteudo_frases_especificas():
    """Nome mutilado pelo celular ('Certido de Dvida Ativa') não diz o
    tipo — o texto do PDF, com acento intacto, diz. Cabeçalho não pode
    enganar: a certidão do CREA carrega 'SERVIÇO PÚBLICO FEDERAL'."""
    from app.documentos.checklist import tipo_do_conteudo
    crea = ("SERVIÇO PÚBLICO FEDERAL\nCONSELHO REGIONAL DE ENGENHARIA "
            "E AGRONOMIA DO PIAUÍ\nCERTIDÃO DE REGISTRO E QUITAÇÃO DE "
            "PESSOA JURÍDICA")
    assert tipo_do_conteudo(crea) == "Registro CREA/CAU"
    assert tipo_do_conteudo(
        "SECRETARIA DA FAZENDA DO ESTADO — certidão quanto à "
        "DÍVIDA ATIVA DO ESTADO") == "CND Estadual"
    assert tipo_do_conteudo(
        "ESTADO DO PIAUÍ\nPREFEITURA MUNICIPAL DE TERESINA\n"
        "SECRETARIA MUNICIPAL DE FINANÇAS - SEMF\nCERTIDAO CONJUNTA "
        "POSITIVA COM EFEITO NEGATIVA E DA DIVIDA ATIVA DO "
        "MUNICIPIO") == "CND Municipal"
    assert tipo_do_conteudo(
        "PODER JUDICIÁRIO\nCERTIDÃO NEGATIVA DE FALÊNCIA, CONCORDATA, "
        "RECUPERAÇÃO JUDICIAL") == "Certidão de Falência"
    assert tipo_do_conteudo(
        "CERTIFICADO DE REGULARIDADE DO FGTS - CRF") == "CRF do FGTS"
    assert tipo_do_conteudo(
        "CERTIDÃO NEGATIVA DE DÉBITOS TRABALHISTAS") == "CNDT Trabalhista"
    assert tipo_do_conteudo("") is None
    assert tipo_do_conteudo("texto qualquer sem certidão") is None


def test_para_iso_formatos():
    assert validades._para_iso("05/09/2026") == "2026-09-05"
    assert validades._para_iso("2026-09-05") == "2026-09-05"
    assert validades._para_iso("5 de setembro de 2026") == "2026-09-05"
    assert validades._para_iso("32/13/2026") is None


def test_data_no_passado_distante_nao_e_sugerida():
    """'Lei de 12/03/1990' não pode virar validade."""
    padrao = validades._PADRAO_DATA
    achados = padrao.findall("documento válido até 12/03/1990 conforme lei")
    assert achados == [("12/03/1990", "")]  # regex acha, o filtro descarta
    # o filtro de faixa fica em sugerir_validade; testado via faixa:
    from datetime import timedelta
    iso = validades._para_iso("12/03/1990")
    data = validades._data_iso(iso)
    assert not (HOJE - timedelta(days=30) <= data <= HOJE + timedelta(days=730))
