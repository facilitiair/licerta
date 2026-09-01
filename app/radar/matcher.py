"""Matcher: decide se uma licitação casa com um perfil de busca (SPEC §5).

Regras de texto: comparação em minúsculas e sem acentos; aspas marcam
expressão exata ("ar condicionado"); asterisco é curinga (pavimenta*).
"""
import re
import unicodedata

from ..config import agora as _agora

# Situações que o PNCP e o Mural do TCE-PI usam. As duas primeiras são as
# disputáveis — é o que um alerta novo já vem marcando por padrão.
SITUACOES_DISPUTAVEIS = ["Divulgada", "Aberta"]
SITUACOES_CONHECIDAS = SITUACOES_DISPUTAVEIS + [
    "Retificada", "Não finalizada", "Suspensa", "Finalizada",
    "Cancelada", "Anulada", "Revogada"]


def esta_vigente(lic, agora=None):
    """A disputa ainda está de pé? Compara o encerramento das propostas com
    o instante atual. Sem data informada não dá para descartar: passa."""
    fim = (lic.data_encerramento_proposta or "").strip().replace(" ", "T")
    if not fim:
        return True
    if len(fim) == 10:
        # Data sem hora (o Mural do TCE-PI às vezes manda só "2026-08-31").
        # Comparar o prefixo curto direto daria "vencida" já à meia-noite do
        # próprio dia da sessão: vale até o fim do dia.
        fim += "T23:59"
    return fim[:16] >= (agora or _agora()).strftime("%Y-%m-%dT%H:%M")


def normalizar(texto):
    """Remove acentos e caixa alta: 'Climatização' -> 'climatizacao'."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


# Como os editais separam as palavras de uma expressão: espaço, hífen (comum
# e os travessões que o Word deixa passar), barra, e a quebra de linha que a
# API às vezes devolve no meio do objeto.
SEPARADORES = r"[\s\-–—/]+"
_SEPARADOR = re.compile(SEPARADORES)


def _termo_para_regex(termo):
    """Converte um termo do perfil num regex sobre o texto normalizado.

    - aspas apenas delimitam a expressão (a busca já é por sequência exata);
    - '*' vira 'zero ou mais letras' — pavimenta* casa pavimentação/pavimentar;
    - o espaço no termo casa qualquer separador: 'ar condicionado' encontra
      'ar-condicionado' e 'ar\ncondicionado' sem precisar de uma linha para
      cada grafia.
    """
    def literal(pedaco):
        return SEPARADORES.join(re.escape(p) for p in _SEPARADOR.split(pedaco) if p)

    termo = normalizar(termo).strip().strip('"').strip()
    partes = [literal(p) for p in termo.split("*")]
    if not any(partes):
        return None       # termo sem nenhuma letra: ver _linha_casa
    return re.compile(r"\w*".join(partes)) if len(partes) > 1 else re.compile(partes[0])


def _linha_casa(texto, linha):
    """Uma linha do perfil casa com o texto?

    Suporta o combinador '+': em 'manutenção + ar condicionado', TODAS as
    partes precisam aparecer no objeto (em qualquer posição) — é a forma de
    pedir algo específico sem exigir a frase exata.

    Linha sem nenhuma letra ('-' usado como separador visual, um '+' solto,
    um '*' sozinho) NÃO casa com nada. Antes ela virava um regex vazio, que
    casa em qualquer posição: uma linha dessas em "palavras a excluir"
    derrubava o banco inteiro e o perfil parava de achar qualquer coisa, sem
    nenhuma explicação na tela.
    """
    regexes = [_termo_para_regex(p) for p in linha.split("+") if p.strip()]
    if not regexes or any(r is None for r in regexes):
        return False
    return all(r.search(texto) for r in regexes)


def texto_casa(objeto, incluir, excluir, modo="ou"):
    """Aplica as listas de palavras ao objeto. Retorna (casou, termos_que_casaram).

    modo='ou': casa se QUALQUER linha casar (padrão).
    modo='e' : casa só se TODAS as linhas casarem.
    Dentro de uma linha, 'a + b' exige as duas; aspas pedem frase exata;
    '*' é curinga.
    """
    texto = normalizar(objeto)
    for termo in excluir or []:
        if termo.strip() and _linha_casa(texto, termo):
            return False, []
    validos = [t for t in (incluir or []) if t.strip()]
    if not validos:
        return True, []          # lista vazia = qualquer objeto interessa
    casados = [t for t in validos if _linha_casa(texto, t)]
    if modo == "e":
        return len(casados) == len(validos), casados
    return bool(casados), casados


def licitacao_casa_perfil(lic, perfil, agora=None):
    """Filtro completo: geografia E modalidade E valor E situação E prazo
    E texto (SPEC §5)."""
    if perfil.ufs and lic.uf not in perfil.ufs:
        return False
    situacoes = getattr(perfil, "situacoes", None) or []
    if situacoes and (lic.situacao or "") not in situacoes:
        return False
    if getattr(perfil, "somente_vigentes", True) and not esta_vigente(lic, agora):
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


def ressintonizar_matches(sessao_db, perfil):
    """Depois que um perfil muda, os casamentos antigos que não casam mais
    SAEM da lista — era o defeito de perfil 'PI' exibindo editais do Acre
    herdados da época em que o perfil era nacional.

    Preserva tudo que tem interação humana (triado no funil, favorito ou
    anotado): decisão de gente não se apaga por edição de filtro.
    Devolve quantos casamentos foram removidos.
    """
    from ..db import Licitacao, PerfilMatch
    removidos = 0
    for m in sessao_db.query(PerfilMatch).filter_by(perfil_id=perfil.id):
        if m.status != "novo" or m.favorito or (m.anotacao or "").strip():
            continue
        lic = sessao_db.get(Licitacao, m.licitacao_id)
        if lic is None or not licitacao_casa_perfil(lic, perfil):
            sessao_db.delete(m)
            removidos += 1
    return removidos
