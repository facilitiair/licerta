import unicodedata


def normalizar(texto):
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def classificar(texto, config):
    """Retorna (categoria, termos_casados) ou (None, None) se não interessa."""
    t = normalizar(texto)
    for termo in config.get("excluir_termos") or []:
        if normalizar(termo) in t:
            return None, None
    categorias = config.get("categorias") or {}
    if not categorias:
        return "geral", ""  # sem categorias configuradas: tudo interessa
    grupos, casados = [], []
    for nome, grupo in categorias.items():
        acertos = [termo for termo in grupo.get("termos", []) if normalizar(termo) in t]
        if acertos:
            grupos.append(nome)
            casados.extend(acertos)
    if not grupos:
        return None, None
    return ",".join(grupos), ", ".join(dict.fromkeys(casados))
