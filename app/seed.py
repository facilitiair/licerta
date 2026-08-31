"""Cargas iniciais: modalidades, municípios do IBGE e perfil de exemplo."""
import logging

from .db import Modalidade, Municipio, Sessao
from .ingestao.pncp import MODALIDADES, baixar_municipios_ibge

log = logging.getLogger("radar.seed")


def semear():
    sessao = Sessao()
    try:
        # Modalidades (SPEC §3.3) — para os checkboxes da interface
        if sessao.query(Modalidade).count() == 0:
            for codigo, nome in MODALIDADES.items():
                sessao.add(Modalidade(codigo=codigo, nome=nome))
            sessao.commit()

        # Municípios do IBGE (SPEC §3.4) — uma vez, na instalação
        if sessao.query(Municipio).count() == 0:
            try:
                municipios = baixar_municipios_ibge()
                sessao.bulk_insert_mappings(Municipio, municipios)
                sessao.commit()
                log.info("IBGE: %s municípios carregados", len(municipios))
            except Exception as e:  # noqa: BLE001 — sem internet, tenta na próxima
                sessao.rollback()
                log.warning("Não foi possível baixar municípios do IBGE: %s", e)

        # Nenhum perfil de exemplo: o produto é genérico e cada empresa define
        # o próprio ramo pela tela de Perfis. Um exemplo pré-carregado de um
        # setor específico só confunde quem compra o app para outro objeto —
        # a tela vazia convida a criar o primeiro perfil.
    finally:
        sessao.close()
