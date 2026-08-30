"""Matcher: decide se uma licitação casa com um perfil de busca (SPEC §5).

Regras de texto: comparação em minúsculas e sem acentos; aspas marcam
expressão exata ("ar condicionado"); asterisco é curinga (pavimenta*).
"""
import re
import unicodedata


def normalizar(texto):
    """Remove acentos e caixa alta: 'Climatização' -> 'climatizacao'."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def _termo_para_regex(termo):
    """Converte um termo do perfil num regex sobre o texto normalizado.

    - aspas apenas delimitam a expressão (a busca já é por sequência exata);
    - '*' vira 'zero ou mais letras' — pavimenta* casa pavimentação/pavimentar.
    """
    termo = normalizar(termo).strip().strip('"').strip()
    partes = [re.escape(p) for p in termo.split("*")]
    return re.compile(r"\w*".join(partes)) if len(partes) > 1 else re.compile(partes[0])


def texto_casa(objeto, incluir, excluir, modo="ou"):
    """Aplica as listas de palavras ao objeto. Retorna (casou, termos_que_casaram).

    modo='ou': casa se QUALQUER termo aparecer (padrão).
    modo='e' : casa só se TODOS os termos aparecerem — busca específica.
    """
    texto = normalizar(objeto)
    for termo in excluir or []:
        if termo.strip() and _termo_para_regex(termo).search(texto):
            return False, []
    validos = [t for t in (incluir or []) if t.strip()]
    if not validos:
        return True, []          # lista vazia = qualquer objeto interessa
    casados = [t for t in validos if _termo_para_regex(t).search(texto)]
    if modo == "e":
        return len(casados) == len(validos), casados
    return bool(casados), casados


def licitacao_casa_perfil(lic, perfil):
    """Filtro completo: geografia E modalidade E valor E texto (SPEC §5)."""
    if perfil.ufs and lic.uf not in perfil.ufs:
        return False
    if perfil.municipios_ibge and str(lic.municipio_ibge) not in \
            [str(m) for m in perfil.municipios_ibge]:
        return False
    if perfil.modalidades and lic.modalidade_codigo not in perfil.modalidades:
        return False
    if perfil.somente_srp and not lic.srp:
        return False
    valor = lic.valor_total_estimado
    if perfil.valor_min is not None and valor is not None and valor < perfil.valor_min:
        return False
    if perfil.valor_max is not None and valor is not None and valor > perfil.valor_max:
        return False
    casou, _ = texto_casa(lic.objeto or "", perfil.palavras_incluir,
                          perfil.palavras_excluir,
                          getattr(perfil, "modo_busca", None) or "ou")
    return casou


CHAVES_ORDENACAO = {
    "abertura_asc": (lambda l: l.data_abertura_proposta or "9999", False),
    "encerramento_asc": (lambda l: l.data_encerramento_proposta or "9999", False),
    "publicacao_desc": (lambda l: l.data_publicacao_pncp or "", True),
    "valor_desc": (lambda l: l.valor_total_estimado or 0, True),
}


def ordenar_licitacoes(lics, ordenacao):
    chave, reverso = CHAVES_ORDENACAO.get(ordenacao,
                                          CHAVES_ORDENACAO["encerramento_asc"])
    return sorted(lics, key=chave, reverse=reverso)
