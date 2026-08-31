"""Testes do matcher (SPEC §10): acentos, expressão exata, exclusão, valor."""
from app.db import PerfilBusca
from app.matcher import licitacao_casa_perfil, normalizar, texto_casa


class LicFake:
    """Licitação mínima para os testes, sem tocar no banco."""
    def __init__(self, **kw):
        self.objeto = kw.get("objeto", "")
        self.uf = kw.get("uf", "PI")
        self.municipio_ibge = kw.get("municipio_ibge", "2211001")
        self.modalidade_codigo = kw.get("modalidade_codigo", 6)
        self.srp = kw.get("srp", False)
        self.valor_total_estimado = kw.get("valor_total_estimado", 100000.0)


def perfil(**kw):
    base = dict(nome="t", ufs=[], municipios_ibge=[], modalidades=[],
                palavras_incluir=[], palavras_excluir=[],
                valor_min=None, valor_max=None, somente_srp=False,
                ordenacao="encerramento_asc", notificar=True)
    base.update(kw)
    return PerfilBusca(**base)


def test_normalizar_remove_acentos_e_caixa():
    assert normalizar("Climatização REFRIGERAÇÃO") == "climatizacao refrigeracao"


def test_palavra_com_acento_casa_objeto_sem_acento():
    casou, termos = texto_casa("aquisicao de sistema de climatizacao",
                               ["climatização"], [])
    assert casou and termos == ["climatização"]


def test_palavra_sem_acento_casa_objeto_com_acento():
    casou, _ = texto_casa("Contratação de REFRIGERAÇÃO industrial",
                          ["refrigeracao"], [])
    assert casou


def test_expressao_exata_com_aspas():
    assert texto_casa("manutenção de ar condicionado central",
                      ['"ar condicionado"'], [])[0]
    assert not texto_casa("ar comprimido e condicionado físico",
                          ['"ar condicionado"'], [])[0]


def test_curinga_asterisco():
    assert texto_casa("obras de pavimentação asfáltica", ["pavimenta*"], [])[0]
    assert texto_casa("serviço de repavimentar vias", ["pavimenta*"], [])[0]
    assert not texto_casa("aquisição de pavilhão", ["pavimenta*"], [])[0]


def test_exclusao_derruba_match():
    casou, _ = texto_casa("locação de veículos com ar condicionado",
                          ["ar condicionado"], ["locação de veículos"])
    assert not casou


def test_inclusao_vazia_casa_qualquer_objeto():
    assert texto_casa("qualquer coisa", [], [])[0]


def test_combinador_mais_exige_partes_na_mesma_linha():
    objeto = "manutenção preventiva e corretiva de aparelhos de ar condicionado"
    # 'a + b': as duas partes precisam aparecer, em qualquer posição
    assert texto_casa(objeto, ["manutenção + ar condicionado"], [])[0]
    assert not texto_casa(objeto, ["manutenção + predial"], [])[0]
    # linhas continuam sendo alternativas (OU entre linhas)
    casou, termos = texto_casa(objeto, ["manutenção + predial",
                                        "manutenção + ar condicionado"], [])
    assert casou and termos == ["manutenção + ar condicionado"]
    # frase exata não casaria (palavras separadas no texto), o '+' sim
    assert not texto_casa(objeto, ['"manutenção de ar condicionado"'], [])[0]


def test_combinador_mais_na_exclusao():
    casou, _ = texto_casa("manutenção da frota de veículos",
                          ["manutenção"], ["manutenção + veículos"])
    assert not casou


def test_modo_e_exige_todas_as_palavras():
    objeto = "manutenção de ar condicionado tipo split"
    assert texto_casa(objeto, ["manutenção", "split"], [], modo="e")[0]
    assert not texto_casa(objeto, ["manutenção", "chiller"], [], modo="e")[0]
    # no modo OU (padrão), uma basta
    assert texto_casa(objeto, ["manutenção", "chiller"], [], modo="ou")[0]


def test_faixa_de_valor():
    p = perfil(valor_min=50000, valor_max=200000)
    assert licitacao_casa_perfil(LicFake(valor_total_estimado=100000), p)
    assert not licitacao_casa_perfil(LicFake(valor_total_estimado=10000), p)
    assert not licitacao_casa_perfil(LicFake(valor_total_estimado=900000), p)
    # valor não informado nunca é barrado pela faixa
    assert licitacao_casa_perfil(LicFake(valor_total_estimado=None), p)


def test_filtro_geografico_e_modalidade():
    p = perfil(ufs=["PI"], modalidades=[6, 8])
    assert licitacao_casa_perfil(LicFake(uf="PI", modalidade_codigo=6), p)
    assert not licitacao_casa_perfil(LicFake(uf="BA", modalidade_codigo=6), p)
    assert not licitacao_casa_perfil(LicFake(uf="PI", modalidade_codigo=4), p)


def test_filtro_municipio():
    p = perfil(municipios_ibge=["2211001"])
    assert licitacao_casa_perfil(LicFake(municipio_ibge="2211001"), p)
    assert not licitacao_casa_perfil(LicFake(municipio_ibge="2200053"), p)


def test_somente_srp():
    p = perfil(somente_srp=True)
    assert licitacao_casa_perfil(LicFake(srp=True), p)
    assert not licitacao_casa_perfil(LicFake(srp=False), p)
