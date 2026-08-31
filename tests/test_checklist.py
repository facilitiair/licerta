"""Testes do checklist exigência × dossiê: mapeamento por palavras,
validade aferida na DATA DA SESSÃO e a honestidade do 'conferir'."""
from datetime import date

from app.documentos import checklist


class DocFake:
    def __init__(self, tipo, validade=None, nome=None, arquivado=False):
        self.tipo = tipo
        self.validade = validade
        self.nome = nome or tipo
        self.arquivado = arquivado


class LicFake:
    data_encerramento_proposta = "2026-09-20T09:00:00"


HOJE = date(2026, 8, 31)


def ficha(**hab):
    base = {"juridica": [], "fiscal_social_trabalhista": [], "tecnica": [],
            "economico_financeira": []}
    base.update(hab)
    return {"habilitacao": base,
            "datas": {"sessao_abertura": "2026-09-20T09:00"}}


# ------------------------------------------------------------- mapeamento
def test_tipos_sugeridos():
    casos = {
        "Certificado de Regularidade do FGTS - CRF": "CRF do FGTS",
        "Certidão Negativa de Débitos Trabalhistas (CNDT)": "CNDT Trabalhista",
        "Prova de regularidade com a Fazenda Federal e Dívida Ativa da União":
            "CND Federal (RFB/PGFN)",
        "Certidão negativa da fazenda estadual": "CND Estadual",
        "Regularidade com a Fazenda Municipal do domicílio":
            "CND Municipal",
        "Certidão negativa de falência ou concordata":
            "Certidão de Falência",
        "Ato constitutivo, estatuto ou contrato social em vigor":
            "Contrato Social",
        "Balanço patrimonial e demonstrações contábeis do último exercício":
            "Balanço Patrimonial",
        "Atestado de capacidade técnica compatível": "Atestado de Capacidade",
        "Registro no CREA da região": "Registro CREA/CAU",
    }
    for exigencia, esperado in casos.items():
        assert checklist.tipo_sugerido(exigencia) == esperado, exigencia


def test_exigencia_sem_mapa_vai_para_conferir():
    assert checklist.tipo_sugerido(
        "Declaração de que não emprega menor de 18 anos") is None


# ------------------------------------------------------ validade na sessão
def test_vigente_hoje_mas_vencendo_antes_da_sessao_alerta():
    """A regra pericial: certidão que vale hoje e morre antes da sessão é
    problema HOJE, não na sessão."""
    docs = [DocFake("CRF do FGTS", validade="2026-09-10")]   # sessão dia 20
    itens, sessao = checklist.avaliar(
        ficha(fiscal_social_trabalhista=["Regularidade do FGTS"]),
        LicFake(), docs, hoje=HOJE)
    assert sessao == date(2026, 9, 20)
    assert itens[0]["veredito"] == "vence_antes"


def test_vigente_ate_depois_da_sessao_e_ok():
    docs = [DocFake("CRF do FGTS", validade="2026-10-15")]
    itens, _ = checklist.avaliar(
        ficha(fiscal_social_trabalhista=["Regularidade do FGTS"]),
        LicFake(), docs, hoje=HOJE)
    assert itens[0]["veredito"] == "ok"


def test_ja_vencido_hoje_e_vencido():
    docs = [DocFake("CRF do FGTS", validade="2026-08-01")]
    itens, _ = checklist.avaliar(
        ficha(fiscal_social_trabalhista=["FGTS"]), LicFake(), docs, hoje=HOJE)
    assert itens[0]["veredito"] == "vencido"


def test_sem_documento_do_tipo_e_falta():
    itens, _ = checklist.avaliar(
        ficha(juridica=["Contrato social em vigor"]), LicFake(),
        [DocFake("CRF do FGTS", "2026-12-01")], hoje=HOJE)
    assert itens[0]["veredito"] == "falta"
    assert itens[0]["tipo"] == "Contrato Social"


def test_usa_o_documento_mais_renovado():
    docs = [DocFake("CRF do FGTS", validade="2026-09-05", nome="antigo"),
            DocFake("CRF do FGTS", validade="2026-12-01", nome="novo")]
    itens, _ = checklist.avaliar(
        ficha(fiscal_social_trabalhista=["FGTS"]), LicFake(), docs, hoje=HOJE)
    assert itens[0]["doc"].nome == "novo" and itens[0]["veredito"] == "ok"


def test_documento_sem_validade_conta_como_nao_vence():
    docs = [DocFake("Contrato Social")]
    itens, _ = checklist.avaliar(
        ficha(juridica=["Ato constitutivo / contrato social"]),
        LicFake(), docs, hoje=HOJE)
    assert itens[0]["veredito"] == "ok"


def test_arquivado_nao_participa():
    docs = [DocFake("CRF do FGTS", "2026-12-01", arquivado=True)]
    itens, _ = checklist.avaliar(
        ficha(fiscal_social_trabalhista=["FGTS"]), LicFake(), docs, hoje=HOJE)
    assert itens[0]["veredito"] == "falta"


def test_sem_data_de_sessao_usa_encerramento_do_portal():
    class SemFichaDatas(LicFake):
        pass
    f = ficha(fiscal_social_trabalhista=["FGTS"])
    f["datas"] = {}
    _, sessao = checklist.avaliar(f, SemFichaDatas(),
                                  [DocFake("CRF do FGTS", "2026-12-01")],
                                  hoje=HOJE)
    assert sessao == date(2026, 9, 20)     # veio do portal
