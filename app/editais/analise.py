"""Ficha do edital analisada por IA (módulo Editais, arquitetura §5).

Orquestra: PDFs já baixados → texto → extração estruturada via LLM →
`edital_fichas`. Os princípios que mandam aqui:

- Processa UMA vez, serve para todos: a ficha é do edital (ativo global),
  nunca do usuário. Pedir de novo devolve a pronta, sem custo novo.
- IA lê, código calcula: a IA transcreve datas e exigências como estão no
  texto; qualquer conta de prazo é feita por código, na hora de exibir.
- Custo visível desde o dia 1: cada geração grava o custo na própria ficha
  (além do log geral em data/ia_custos.jsonl).
"""
import json
import logging
import os

from ia import camadas, cliente

from ..config import PASTA_DADOS, agora
from ..db import ArquivoEdital, EditalFicha

log = logging.getLogger("radar.editais")

# Versão do prompt gravada na ficha: quando o prompt mudar de forma
# relevante, subir aqui — fichas antigas ficam identificáveis.
VERSAO_PROMPT = "ficha-edital/1"

# Teto de texto enviado à IA. Editais de obra passam de mil páginas com
# planilhas; além do custo, o excedente é quase sempre repetição de anexo.
# ~300 mil caracteres ≈ 90 mil tokens ≈ US$ 0,30 por edital no modelo forte.
LIMITE_CARACTERES = 300_000


# Erro compartilhado da camada de IA — definido lá; reexportado aqui porque
# main.py e os testes o conhecem por este caminho.
from ia.cliente import SemChaveIA  # noqa: E402,F401


def extrair_texto_pdfs(arquivos):
    """Texto dos PDFs baixados, com cabeçalho por arquivo. Devolve (texto,
    lidos): PDF escaneado (imagem, sem camada de texto) conta como não lido.
    """
    from pypdf import PdfReader
    partes, lidos = [], []
    tamanho = 0
    for arq in arquivos:
        caminho = os.path.join(PASTA_DADOS, arq.caminho_local or "")
        if not (arq.caminho_local and os.path.exists(caminho)):
            continue
        try:
            paginas = []
            for pagina in PdfReader(caminho).pages:
                paginas.append(pagina.extract_text() or "")
                if tamanho + sum(len(p) for p in paginas) > LIMITE_CARACTERES:
                    break
            texto = "\n".join(paginas).strip()
        except Exception as e:  # noqa: BLE001 — um PDF corrompido não trava o resto
            log.warning("PDF ilegível %s: %s", arq.caminho_local, e)
            continue
        if len(texto) < 200:
            continue        # escaneado ou vazio: só imagem, nada a extrair
        partes.append(f"===== ARQUIVO: {arq.titulo or ''} ({arq.tipo or ''}) "
                      f"=====\n{texto}")
        lidos.append(arq)
        tamanho += len(texto)
        if tamanho >= LIMITE_CARACTERES:
            break
    return "\n\n".join(partes)[:LIMITE_CARACTERES], lidos


def _validar_ficha(texto_json):
    """A resposta precisa ser um objeto com o esqueleto do esquema.

    Validação de forma, não de conteúdo: o que interessa é a tela nunca
    quebrar por chave ausente ou tipo trocado.
    """
    dados = json.loads(texto_json)
    if not isinstance(dados, dict):
        raise ValueError("resposta não é um objeto JSON")
    dados.setdefault("resumo", "")
    # Todo campo escalar existe, nem que seja None: no Jinja, chave ausente
    # vira Undefined — que NÃO é none e passa nos guards da tela.
    for chave in ("objeto_detalhado", "lei_base", "criterio_julgamento",
                  "modo_disputa", "julgamento_por", "srp",
                  "consorcio_permitido", "exclusivo_me_epp",
                  "cota_reservada_me_epp", "exige_visita_tecnica",
                  "visita_tecnica_detalhe", "valor_estimado",
                  "prazo_execucao", "vigencia_contrato", "garantia_proposta",
                  "garantia_contratual", "aceitabilidade_precos",
                  "analise_incompleta"):
        dados.setdefault(chave, None)
    dados.setdefault("riscos", [])
    dados.setdefault("pontos_atencao", [])
    dados.setdefault("anexos_citados_ausentes", [])
    dados.setdefault("proposta_forma", [])
    if not isinstance(dados.get("habilitacao"), dict):
        dados["habilitacao"] = {}
    for bloco in ("juridica", "fiscal_social_trabalhista", "tecnica",
                  "economico_financeira"):
        if not isinstance(dados["habilitacao"].get(bloco), list):
            dados["habilitacao"][bloco] = []
    if not isinstance(dados.get("datas"), dict):
        dados["datas"] = {}
    if not isinstance(dados["riscos"], list):
        dados["riscos"] = []
    for lista in ("pontos_atencao", "anexos_citados_ausentes",
                  "proposta_forma"):
        if not isinstance(dados[lista], list):
            dados[lista] = [str(dados[lista])]
    return dados


def _mensagem(lic, texto_pdfs):
    """Monta a mensagem: metadados que JÁ temos + o texto dos documentos."""
    meta = {
        "numero_controle_pncp": lic.numero_controle_pncp,
        "orgao": lic.orgao_nome, "municipio": lic.municipio_nome,
        "uf": lic.uf, "modalidade": lic.modalidade_nome,
        "objeto_resumido": lic.objeto,
        "valor_estimado_portal": lic.valor_total_estimado,
        "abertura_proposta": lic.data_abertura_proposta,
        "encerramento_proposta": lic.data_encerramento_proposta,
        "srp_portal": lic.srp,
    }
    return ("METADADOS DO PORTAL (já estruturados, use para conferir):\n"
            + json.dumps(meta, ensure_ascii=False, indent=1)
            + "\n\nTEXTO DO EDITAL E ANEXOS:\n\n" + texto_pdfs)


def _custo_da_ultima_chamada():
    """Custo da última linha do log de IA — a chamada que acabou de rodar."""
    try:
        with open(cliente.CAMINHO_CUSTOS, "rb") as f:
            ultima = f.read().decode("utf-8").strip().rsplit("\n", 1)[-1]
        return float(json.loads(ultima).get("custo_usd", 0.0))
    except (OSError, ValueError, KeyError):
        return 0.0


def analisar_edital(sessao_db, lic, forcar=False):
    """Gera (ou devolve) a ficha estruturada de uma licitação.

    Devolve a EditalFicha — com `ficha_json` preenchido no sucesso, ou com
    `erro` explicando o que impediu (sem PDF, PDF escaneado, IA fora do ar).
    Ficha pronta só é regerada com `forcar=True`.
    """
    ficha = (sessao_db.query(EditalFicha)
             .filter_by(licitacao_id=lic.id).first())
    if ficha and ficha.ficha_json and not forcar:
        return ficha
    if not os.environ.get("ANTHROPIC_API_KEY", ""):
        raise SemChaveIA(
            "A análise por IA está desligada: falta a chave da API "
            "(ANTHROPIC_API_KEY). O administrador configura em /config.")
    if ficha is None:
        ficha = EditalFicha(licitacao_id=lic.id)
        sessao_db.add(ficha)

    arquivos = (sessao_db.query(ArquivoEdital)
                .filter_by(licitacao_id=lic.id).all())
    if not arquivos:
        # Melhor esforço: busca os documentos agora, na hora do clique.
        from .arquivos import baixar_arquivos
        try:
            baixar_arquivos(sessao_db, lic)
        except Exception:  # noqa: BLE001
            log.exception("Download na hora da análise falhou (lic %s)", lic.id)
        arquivos = (sessao_db.query(ArquivoEdital)
                    .filter_by(licitacao_id=lic.id).all())

    texto, lidos = extrair_texto_pdfs(arquivos)
    if not texto:
        ficha.erro = ("Nenhum texto extraível: " +
                      ("a licitação não tem documento publicado no PNCP."
                       if not arquivos else
                       "os PDFs parecem escaneados (só imagem). Abra o "
                       "documento pelo link e leia manualmente."))
        ficha.ficha_json = ""
        ficha.gerada_em = agora()
        sessao_db.commit()
        return ficha
    try:
        resposta = cliente.chamar(
            job="ficha_edital",
            prompt_sistema=cliente.carregar_prompt("ficha-edital"),
            mensagem=_mensagem(lic, texto),
            modelo=camadas.EXTRACAO, max_tokens=16000, json_estrito=True)
        dados = _validar_ficha(resposta)
    except Exception:  # noqa: BLE001 — falha vira erro legível na ficha
        # O motivo técnico fica no log (e no aviso do vigia, se persistir);
        # a tela fala a língua do usuário (UI §7), nunca HTTP nem stack.
        log.exception("Análise da licitação %s falhou", lic.id)
        ficha.erro = ("A análise não terminou desta vez. Tente de novo em "
                      "instantes.")
        ficha.gerada_em = agora()
        sessao_db.commit()
        return ficha
    ficha.ficha_json = json.dumps(dados, ensure_ascii=False)
    ficha.erro = ""
    ficha.modelo = camadas.EXTRACAO
    ficha.versao_prompt = VERSAO_PROMPT
    ficha.custo_usd = _custo_da_ultima_chamada()
    ficha.caracteres_lidos = len(texto)
    ficha.gerada_em = agora()
    sessao_db.commit()
    log.info("Ficha da licitação %s gerada (%s caracteres, US$ %.4f)",
             lic.id, len(texto), ficha.custo_usd)
    return ficha
