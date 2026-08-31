"""Testes da Fase 3: mapeamento de atas, parser do Mural TCE-PI."""
from app.pncp import mapear_ata
from app.tcepi import _mapear, _modalidade

ATA = {
    "numeroControlePNCPAta": "18457226000181-1-000015/2023-000001",
    "numeroControlePNCPCompra": "18457226000181-1-000015/2023",
    "numeroAtaRegistroPreco": "NPERP 003/2023",
    "anoAta": 2023,
    "cancelado": False,
    "dataAssinatura": "2023-06-16",
    "vigenciaInicio": "2023-07-07",
    "vigenciaFim": "2026-10-07",
    "objetoContratacao": "Registro de preços de ar condicionado",
    "cnpjOrgao": "18457226000181",
    "nomeOrgao": "MUNICIPIO DE TESTE",
    "nomeUnidadeOrgao": "SECRETARIA",
    "possibilidadeAdesao": True,
}


def test_mapear_ata_campos_reais():
    m = mapear_ata(ATA)
    assert m["numero_controle_ata"] == "18457226000181-1-000015/2023-000001"
    assert m["vigencia_fim"] == "2026-10-07"
    assert m["possibilidade_adesao"] is True
    # link aponta para a página da compra (que lista as atas)
    assert m["link_pncp"] == "https://pncp.gov.br/app/editais/18457226000181/2023/15"


def test_modalidade_tce_para_codigo_pncp():
    assert _modalidade("Concorrência", "Eletrônica")[0] == 4
    assert _modalidade("Pregão", "Presencial")[0] == 7
    assert _modalidade("Dispensa de Licitação", "")[0] == 8
    assert _modalidade("Modalidade Nova Desconhecida", "")[0] is None


LINHA_MURAL = (
    '<td>PREFEITURA MUNICIPAL DE PAVUSSU</td><td>MUNICIPAL</td>'
    '<td>LW-009406/26</td><td>Concorrência nº 058/2026</td>'
    '<td>Lei nº 14.133/21</td><td>Concorrência</td><td>Eletrônica</td>'
    '<td>Menor preço</td><td>Obras e Serviços de Engenharia</td>'
    '<td>Pavimentação em Paralelepípedo na zona urbana</td>'
    '<td>15/09/2026 09:00</td><td>15/09/2026</td><td>499.633,6300</td>'
    '<td>499.633,63</td><td>Divulgada</td><td>30/08/2026</td><td></td>'
    '<td></td><td></td><td>30/08/2026</td><td>30/08/2026</td>'
    '<td><a href="detalhelicitacao.xhtml?id=1174120">link</a></td>'
)


def test_dedup_por_municipio_e_valor():
    from app.coleta import e_duplicata_tcepi
    chaves = {("obj", "pavimentacao em paralelepipedo na zona urbana"),
              ("mv", "pavussu", "499633.63")}
    # texto diferente, mas mesmo município e valor -> duplicata
    assert e_duplicata_tcepi({"objeto": "OUTRO TEXTO qualquer",
                              "municipio_nome": "Pavussu",
                              "valor_total_estimado": 499633.63}, chaves)
    # mesmo município, valor diferente -> não é duplicata
    assert not e_duplicata_tcepi({"objeto": "OUTRO TEXTO",
                                  "municipio_nome": "Pavussu",
                                  "valor_total_estimado": 1000.0}, chaves)
    # sem valor, texto igual (normalizado) -> duplicata
    assert e_duplicata_tcepi({"objeto": "PAVIMENTAÇÃO EM PARALELEPÍPEDO NA "
                                        "ZONA URBANA",
                              "municipio_nome": None,
                              "valor_total_estimado": None}, chaves)


def test_parser_do_mural():
    item = _mapear(LINHA_MURAL)
    assert item["numero_controle_pncp"] == "TCEPI-LW-009406/26"
    assert item["fonte"] == "tcepi"
    assert item["modalidade_codigo"] == 4
    assert item["municipio_nome"] == "Pavussu"
    assert item["uf"] == "PI"
    assert item["valor_total_estimado"] == 499633.63
    assert item["data_abertura_proposta"] == "2026-09-15T09:00:00"
    assert "1174120" in item["link_sistema_origem"]


# --- município do Mural: sem ele a deduplicação contra o PNCP não funciona ---
def test_municipio_sai_do_nome_abreviado_do_orgao():
    """O Mural escreve 'P. M. DE X', não 'PREFEITURA MUNICIPAL DE X'. Só com
    a forma por extenso, o município ficava nulo nas 470 linhas coletadas."""
    from app.tcepi import municipio_do_orgao
    assert municipio_do_orgao("P. M. DE BETANIA DO PIAUI") == "Betania Do Piaui"
    assert municipio_do_orgao("P.M. DE OEIRAS") == "Oeiras"
    assert municipio_do_orgao("PREFEITURA MUNICIPAL DE TERESINA") == "Teresina"
    assert municipio_do_orgao("CÂMARA MUNICIPAL DE PICOS") == "Picos"
    assert municipio_do_orgao("C. M. DE FLORIANO") == "Floriano"


def test_orgao_que_nao_e_municipio_devolve_nada():
    from app.tcepi import municipio_do_orgao
    assert municipio_do_orgao("SETRANS - SECRETARIA DOS TRANSPORTES") is None
    assert municipio_do_orgao("") is None
    assert municipio_do_orgao(None) is None


def test_duplicata_do_mural_e_reconhecida_por_municipio_e_valor():
    """Os dois sistemas escrevem o objeto diferente; município+valor é a
    assinatura que pega o mesmo edital nas duas fontes."""
    from app.coleta import chaves_dedup_pncp, e_duplicata_tcepi

    class Consulta:
        def filter(self, *_):
            return [("[Portal] - AQUISIÇÃO DE ANALISADOR, DESTINADO A...",
                     "Ribeiro Gonçalves", 127450.0, "2026-09-10T09:00:00")]

    class SessaoFake:
        def query(self, *_):
            return Consulta()

    chaves = chaves_dedup_pncp(SessaoFake())
    do_mural = {"objeto": "AQUISIÇÃO DE ANALISADOR S1600, DESTINADO A...",
                "municipio_nome": "Ribeiro Goncalves",   # sem cedilha, do Mural
                "valor_total_estimado": 127450.0}
    assert e_duplicata_tcepi(do_mural, chaves)
    outro = dict(do_mural, valor_total_estimado=999.0,
                 objeto="OUTRA COISA COMPLETAMENTE DIFERENTE")
    assert not e_duplicata_tcepi(outro, chaves)
