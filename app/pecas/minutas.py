"""Peças jurídicas sob demanda (arquitetura §5 e §7, camada 3).

Por enquanto: minuta de IMPUGNAÇÃO ao edital, gerada a partir da ficha
(riscos) + texto do edital + identidade da empresa. Os princípios:

- Peça é MINUTA, nunca peça final (princípio 5): a trava de rascunho vai
  no prompt E na tela, e a geração se recusa quando o prazo já passou —
  protocolo intempestivo é pior que nenhum.
- O prazo entra CALCULADO por código (art. 164 via acompanhamento/prazos);
  a IA transcreve a conta, não a refaz.
- Sob demanda = custo atribuível: cada minuta grava o próprio custo e
  quem pediu.
"""
import json
import logging

from ia import camadas, cliente

from ..acompanhamento.prazos import prazos_da_sessao
from ..config import hoje as hoje_local
from ..db import EmpresaDados, Minuta
from ..documentos.checklist import data_da_sessao
from ..editais.analise import extrair_texto_pdfs, _custo_da_ultima_chamada

log = logging.getLogger("radar.pecas")

LIMITE_TEXTO_EDITAL = 150_000    # a minuta precisa das cláusulas, não do TR inteiro


class MinutaIndevida(RuntimeError):
    """Situação em que gerar a minuta seria um desserviço (prazo vencido,
    sem riscos apontados) — a mensagem explica o caminho alternativo."""


def dados_empresa(sessao_db, usuario_id=None):
    """A identidade da empresa DESTA conta (cria vazia se não existir)."""
    dados = (sessao_db.query(EmpresaDados)
             .filter_by(usuario_id=usuario_id).first())
    if dados is None:
        dados = EmpresaDados(usuario_id=usuario_id)
        sessao_db.add(dados)
        sessao_db.commit()
    return dados


def _prazo_texto(prazos):
    if not prazos:
        return ("Data da sessão não informada no portal — a tempestividade "
                "precisa ser conferida manualmente antes do protocolo.")
    limite = prazos["limite_impugnacao"].strftime("%d/%m/%Y")
    return (f"Prazo do art. 164 calculado pela plataforma: protocolo até "
            f"{limite} (3 dias úteis antes da sessão, contados com feriados "
            f"nacionais; feriado local do órgão pode recuar a data). "
            f"Restam {prazos['dias_uteis_para_impugnar']} dia(s) útil(eis).")


def gerar_impugnacao(sessao_db, lic, ficha_dados, usuario=None, hoje=None):
    """Gera a minuta de impugnação. Devolve a Minuta gravada.

    Levanta MinutaIndevida (com explicação) quando não deve gerar, e
    SemChaveIA quando a IA está desligada.
    """
    hoje = hoje or hoje_local()
    riscos = (ficha_dados or {}).get("riscos") or []
    if not ficha_dados:
        raise MinutaIndevida("Gere primeiro a ficha do edital (botão "
                             "'Analisar edital com IA'): a impugnação parte "
                             "dos riscos apontados nela.")
    if not riscos:
        raise MinutaIndevida("A ficha não aponta cláusula de risco — não há "
                             "o que impugnar. Se você enxergou um vício que "
                             "a ficha não pegou, regere a ficha ou consulte "
                             "diretamente um advogado.")
    prazos = prazos_da_sessao(data_da_sessao(ficha_dados, lic), hoje)
    if prazos and prazos["impugnacao_passou"]:
        raise MinutaIndevida(
            "O prazo de impugnação (art. 164) JÁ PASSOU — protocolar agora "
            "seria intempestivo. Caminhos que restam: pedido de "
            "esclarecimento, representação ao tribunal de contas ou via "
            "judicial — todos pedem orientação jurídica humana.")
    cliente.exigir_chave()

    from ..db import ArquivoEdital
    arquivos = (sessao_db.query(ArquivoEdital)
                .filter_by(licitacao_id=lic.id).all())
    texto_edital, _ = extrair_texto_pdfs(arquivos)
    empresa = dados_empresa(sessao_db, getattr(usuario, "id", None))
    entrada = {
        "ficha_edital": {
            "modalidade": lic.modalidade_nome,
            "numero": f"{lic.numero_compra}/{lic.ano_compra}",
            "orgao": lic.orgao_nome,
            "municipio_uf": f"{lic.municipio_nome}/{lic.uf}",
            "objeto": lic.objeto,
            "processo": lic.processo,
            "sessao": (ficha_dados.get("datas") or {}).get("sessao_abertura")
                      or lic.data_encerramento_proposta,
        },
        "riscos_para_atacar": riscos,
        "dados_da_empresa": {
            "razao_social": empresa.razao_social or "[PREENCHER: razão social]",
            "cnpj": empresa.cnpj or "[PREENCHER: CNPJ]",
            "endereco": empresa.endereco or "[PREENCHER: endereço]",
            "representante": empresa.representante_nome
                             or "[PREENCHER: representante]",
            "cargo": empresa.representante_cargo or "[PREENCHER: cargo]",
        },
        "prazo_calculado": _prazo_texto(prazos),
        "data_de_hoje": hoje.strftime("%d/%m/%Y"),
    }
    mensagem = (json.dumps(entrada, ensure_ascii=False, indent=1)
                + "\n\nTEXTO DO EDITAL (recorte):\n\n"
                + texto_edital[:LIMITE_TEXTO_EDITAL])
    texto = cliente.chamar(
        job="minuta_impugnacao",
        prompt_sistema=cliente.carregar_prompt("minuta-impugnacao"),
        mensagem=mensagem, modelo=camadas.GERACAO, max_tokens=16000)
    if "MINUTA" not in texto[:400].upper():
        # A trava de rascunho é inegociável: se o modelo a omitiu, nós a
        # colocamos — nunca sai peça sem o aviso.
        texto = ("> ⚠️ **MINUTA GERADA POR IA — RASCUNHO.** Revisão "
                 "obrigatória por advogado ou responsável habilitado antes "
                 "do protocolo.\n\n" + texto)
    minuta = Minuta(licitacao_id=lic.id, tipo="impugnacao", texto=texto,
                    modelo=camadas.GERACAO,
                    custo_usd=_custo_da_ultima_chamada(),
                    criado_por=getattr(usuario, "id", None))
    sessao_db.add(minuta)
    sessao_db.commit()
    log.info("Minuta de impugnação gerada para a licitação %s (US$ %.4f)",
             lic.id, minuta.custo_usd)
    return minuta
