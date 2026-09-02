"""A ficha do edital como DOCUMENTO — Word e PDF, não só bloco na tela.

A ficha nasce como JSON (ativo global, 1× por edital). Aqui ela vira um
relatório em markdown, o mesmo que docx_export/pdf_export sabem paginar,
para o usuário baixar, imprimir, anexar ao processo interno ou mandar
para o contador. Tudo determinístico: nenhuma chamada de IA.
"""


def _quando(iso):
    from ..main import _filtro_quando
    return _filtro_quando(iso) if iso else "não informado"


def _sim_nao(valor):
    if valor is True:
        return "sim"
    if valor is False:
        return "não"
    return "não informado"


def _lista(titulo, itens):
    if not itens:
        return []
    return [f"## {titulo}", ""] + [f"- {item}" for item in itens] + [""]


def ficha_para_markdown(lic, dados, ficha=None, prazos=None):
    """Markdown completo da ficha, pronto para virar .docx ou .pdf."""
    dados = dados or {}
    datas = dados.get("datas") or {}
    hab = dados.get("habilitacao") or {}
    linhas = [
        f"# Ficha do edital — {lic.modalidade_nome or 'Licitação'} "
        f"{lic.numero_compra or ''}"
        + (f"/{lic.ano_compra}" if lic.ano_compra and
           not (lic.numero_compra or "").endswith(f"/{lic.ano_compra}")
           else ""),
        "",
        f"**Órgão:** {lic.orgao_nome or 'não informado'}  ",
        f"**Local:** {lic.municipio_nome or ''}/{lic.uf or ''}  ",
        f"**Objeto:** {lic.objeto or ''}  ",
        f"**Abertura da sessão:** {_quando(lic.data_encerramento_proposta)}  ",
        f"**Valor estimado (portal):** "
        + ("R$ {:,.2f}".format(lic.valor_total_estimado).replace(",", "X")
           .replace(".", ",").replace("X", ".")
           if lic.valor_total_estimado else "não informado") + "  ",
        f"**Nº no portal:** {lic.numero_controle_pncp}",
        "",
    ]
    if ficha is not None and getattr(ficha, "gerada_em", None):
        linhas.append(f"*Análise automática de "
                      f"{ficha.gerada_em.strftime('%d/%m/%Y %H:%M')}"
                      + (f" · {len(dados.get('revisoes') or [])} passada(s) "
                         "de pente fino" if dados.get("revisoes") else "")
                      + "*")
        linhas.append("")
    if dados.get("analise_incompleta"):
        linhas += ["> **Análise incompleta:** "
                   f"{dados['analise_incompleta']}", ""]
    linhas += ["## Resumo", "", dados.get("resumo") or "não informado", ""]
    if dados.get("objeto_detalhado"):
        linhas += ["## Objeto detalhado", "", dados["objeto_detalhado"], ""]

    linhas += ["## Condições da disputa", "",
               "| Item | Valor |", "|---|---|"]
    for rotulo, valor in [
            ("Lei", dados.get("lei_base")),
            ("Critério de julgamento", dados.get("criterio_julgamento")),
            ("Julgamento por", dados.get("julgamento_por")),
            ("Modo de disputa", dados.get("modo_disputa")),
            ("Registro de preços (SRP)", _sim_nao(dados.get("srp"))),
            ("Exclusivo ME/EPP", _sim_nao(dados.get("exclusivo_me_epp"))),
            ("Cota reservada ME/EPP",
             _sim_nao(dados.get("cota_reservada_me_epp"))),
            ("Consórcio permitido", _sim_nao(dados.get("consorcio_permitido"))),
            ("Visita técnica", _sim_nao(dados.get("exige_visita_tecnica"))),
            ("Detalhe da visita", dados.get("visita_tecnica_detalhe")),
            ("Prazo de execução", dados.get("prazo_execucao")),
            ("Vigência do contrato", dados.get("vigencia_contrato")),
            ("Garantia de proposta", dados.get("garantia_proposta")),
            ("Garantia contratual", dados.get("garantia_contratual")),
            ("Aceitabilidade de preços", dados.get("aceitabilidade_precos"))]:
        linhas.append(f"| {rotulo} | {valor if valor not in (None, '') else 'não informado'} |")
    linhas.append("")

    linhas += ["## Datas", "", "| Marco | Data |", "|---|---|",
               f"| Sessão / abertura | {_quando(datas.get('sessao_abertura'))} |",
               f"| Limite para impugnação | "
               f"{_quando(datas.get('limite_impugnacao'))} |",
               f"| Limite para esclarecimentos | "
               f"{_quando(datas.get('limite_esclarecimentos'))} |"]
    if prazos:
        linhas.append(
            f"| Prazo calculado pela plataforma | "
            f"{prazos['dias_uteis_restantes']} dia(s) útil(eis) até a sessão; "
            f"impugnação até {prazos['limite_impugnacao'].strftime('%d/%m/%Y')} "
            "(art. 164; feriado local pode recuar) |")
    linhas.append("")

    riscos = dados.get("riscos") or []
    if riscos:
        linhas += ["## Pontos de risco", ""]
        for r in riscos:
            if isinstance(r, dict):
                linhas.append(f"- **{r.get('clausula') or '—'}**: "
                              f"{r.get('motivo') or ''}")
            else:
                linhas.append(f"- {r}")
        linhas.append("")
    linhas += _lista("Habilitação jurídica", hab.get("juridica"))
    linhas += _lista("Regularidade fiscal, social e trabalhista",
                     hab.get("fiscal_social_trabalhista"))
    linhas += _lista("Qualificação técnica", hab.get("tecnica"))
    linhas += _lista("Qualificação econômico-financeira",
                     hab.get("economico_financeira"))
    linhas += _lista("Forma da proposta", dados.get("proposta_forma"))
    linhas += _lista("Pontos de atenção", dados.get("pontos_atencao"))
    linhas += _lista("Anexos citados que não vieram",
                     dados.get("anexos_citados_ausentes"))
    for n, rev in enumerate(dados.get("revisoes") or [], start=1):
        linhas += _lista(f"Pente fino nº {n} ({rev.get('quando', '')}) — "
                         "o que foi acrescentado ou corrigido",
                         rev.get("achados") or ["nada a acrescentar"])
    linhas += ["---", "",
               "A ficha é um resumo automático do texto publicado. Confira "
               "sempre no edital antes de decidir; datas e prazos calculados "
               "consideram feriados nacionais."]
    return "\n".join(linhas)
