"""Normalização de texto para a interface (Regras de UI §6).

O PNCP grita em CAIXA ALTA; a tela fala em sentence case. A conversão é
feita SEMPRE por esta função — o original fica intacto no banco. Siglas
conhecidas sobrevivem em maiúsculas.
"""
import re

# Siglas que permanecem em maiúsculas mesmo em sentence case. Uma lista
# só, usada em toda a interface — cresceu? cresce aqui.
SIGLAS = {
    "SRP", "CND", "CNDT", "CRF", "ME", "EPP", "ME/EPP", "UASG", "PNCP",
    "TCE", "TCE-PI", "CNPJ", "CPF", "FGTS", "INSS", "RFB", "PGFN", "BDI",
    "ART", "CAT", "CREA", "CAU", "TR", "ETP", "PPRA", "PCMSO", "EPI",
    "LTDA", "EIRELI", "S/A", "TI", "GLP", "PABX", "CFTV", "VRF", "PMCF",
    "UBS", "USF", "CRAS", "CREAS", "CAPS", "EMEF", "EMEI", "IFPI", "UFPI",
}

_GRITADO = 0.7          # fração de maiúsculas a partir da qual normalizamos


def sentenca(texto):
    """Sentence case para texto gritado; texto já bem escrito fica em paz.

    'CONTRATAÇÃO DE EMPRESA PARA MANUTENÇÃO (SRP)' →
    'Contratação de empresa para manutenção (SRP)'.
    """
    if not texto:
        return texto
    letras = [c for c in texto if c.isalpha()]
    if not letras:
        return texto
    if sum(c.isupper() for c in letras) / len(letras) < _GRITADO:
        return texto                     # não está gritado: não mexe
    plano = texto.lower()

    # Primeira letra do texto e de cada frase voltam a maiúscula
    def _capitalizar(m):
        return m.group(1) + m.group(2).upper()
    plano = re.sub(r"(^|[.!?]\s+)(\w)", _capitalizar, plano)

    # Siglas conhecidas voltam a maiúsculas (por palavra inteira)
    def _sigla(m):
        candidata = m.group(0).upper()
        return candidata if candidata in SIGLAS else m.group(0)
    plano = re.sub(r"\b[\w/]{2,6}\b", _sigla, plano)
    return plano
