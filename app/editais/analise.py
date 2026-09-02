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
import threading

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
    lidos). PDF escaneado (só imagem) é transcrito por visão (ia/ocr) —
    só conta como não lido se nem assim houver texto.
    """
    from pypdf import PdfReader
    from ia import ocr
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
            texto = ""
        if ocr.pdf_precisa_de_ocr(texto):
            try:
                texto = ocr.transcrever_pdf(caminho, job="ocr_edital")
            except Exception as e:  # noqa: BLE001 — OCR falhou: segue sem ele
                log.warning("OCR de %s falhou: %s", arq.caminho_local, e)
                texto = ""
        if not texto.strip():
            continue        # nem imagem legível: nada a extrair
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
    # Item de lista tem de ser TEXTO: o modelo às vezes devolve
    # {"documento": "...", "observacao": "..."} e a tela/checklist
    # esperam string (era 500 em ficha antiga).
    for bloco in ("juridica", "fiscal_social_trabalhista", "tecnica",
                  "economico_financeira"):
        dados["habilitacao"][bloco] = [_como_texto(i) for i in
                                       dados["habilitacao"][bloco]]
    for lista in ("pontos_atencao", "anexos_citados_ausentes",
                  "proposta_forma"):
        dados[lista] = [_como_texto(i) for i in dados[lista]]
    dados["riscos"] = [r if isinstance(r, dict)
                       else {"clausula": "", "motivo": _como_texto(r)}
                       for r in dados["riscos"]]
    dados["datas"] = {k: (v if isinstance(v, str) or v is None
                          else _como_texto(v))
                      for k, v in dados["datas"].items()}
    if not isinstance(dados.get("revisoes"), list):
        dados.pop("revisoes", None)
    return dados


def _como_texto(item):
    """Item de lista como uma linha legível, seja string, dict ou lista."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return "; ".join(f"{k}: {v}" for k, v in item.items() if v)
    if isinstance(item, (list, tuple)):
        return "; ".join(_como_texto(i) for i in item)
    return "" if item is None else str(item)


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


def _motivo_sem_texto(lic):
    """Por que não há documento para ler? Consulta o portal e diz a verdade.

    Distingue os três mundos que antes viravam a mesma frase (e uma frase
    errada): o órgão realmente não publicou nada, o portal listou mas o
    download falhou agora, ou o portal nem respondeu.
    """
    if lic.fonte != "pncp":
        return ("os documentos desta fonte não ficam no PNCP. Abra o portal "
                "de origem para ler o edital.")
    from ..ingestao.pncp import listar_arquivos_compra
    from .arquivos import _sequencial
    seq = _sequencial(lic.numero_controle_pncp)
    try:
        docs = (listar_arquivos_compra(lic.orgao_cnpj, lic.ano_compra, seq)
                if seq and lic.orgao_cnpj and lic.ano_compra else [])
        ativos = [d for d in docs if d.get("statusAtivo", True)]
    except Exception:  # noqa: BLE001 — portal fora do ar não é culpa do órgão
        return ("o PNCP não respondeu agora. Tente de novo em instantes.")
    if ativos:
        return ("os documentos existem no PNCP, mas o download não funcionou "
                "agora. Tente de novo em instantes.")
    return ("o órgão ainda não publicou os arquivos desta licitação no "
            "PNCP. O edital deve estar no portal do órgão — use o link "
            "\"Sistema de origem\" desta página.")


def precisa_de_ocr(arquivos):
    """Algum PDF deste edital exige leitura por imagem AINDA não feita?

    Decide se a análise cabe no clique (texto nativo: 20–60 s) ou vai para
    segundo plano (páginas digitalizadas: minutos de transcrição).
    """
    from pypdf import PdfReader
    from ia import ocr
    for arq in arquivos:
        caminho = os.path.join(PASTA_DADOS, arq.caminho_local or "")
        if not (arq.caminho_local and os.path.exists(caminho)):
            continue
        if os.path.exists(caminho + ocr.SUFIXO_CACHE):
            continue                     # já transcrito: é instantâneo
        try:
            nativo = "".join((p.extract_text() or "")
                             for p in PdfReader(caminho).pages[:3])
        except Exception:  # noqa: BLE001
            continue
        if ocr.pdf_precisa_de_ocr(nativo):
            return True
    return False


# Análises longas (OCR) em andamento — uma por licitação, como na perícia.
_em_andamento = set()
_trava = threading.Lock()


def em_andamento(lic_id):
    with _trava:
        return lic_id in _em_andamento


def _rodar_em_fundo(lic_id, forcar, pente_fino=False):
    from ..db import Licitacao, Sessao
    s = Sessao()
    try:
        lic = s.get(Licitacao, lic_id)
        if lic is not None and pente_fino:
            pente_fino_da_ficha(s, lic)
        elif lic is not None:
            analisar_edital(s, lic, forcar=forcar)
    except Exception:  # noqa: BLE001 — a ficha grava o erro; aqui só log
        log.exception("Análise em segundo plano da licitação %s falhou", lic_id)
    finally:
        s.close()
        with _trava:
            _em_andamento.discard(lic_id)


def iniciar_em_fundo(lic_id, forcar=False, pente_fino=False):
    """Dispara a análise (ou o pente fino) numa thread. False se já há
    uma em andamento para esta licitação."""
    with _trava:
        if lic_id in _em_andamento:
            return False
        _em_andamento.add(lic_id)
    threading.Thread(target=_rodar_em_fundo,
                     args=(lic_id, forcar, pente_fino), daemon=True).start()
    return True


VERSAO_PROMPT_PENTE_FINO = "ficha-pente-fino/1"


def pente_fino_da_ficha(sessao_db, lic):
    """Segunda leitura do edital inteiro, no modelo forte, sobre a ficha
    que já existe: corrige, completa e registra o que mudou.

    A pedido do dono do produto (02/09/2026): "reanalisar e passar o
    pente fino outras vezes caso tenha deixado algo importante passar".
    Cada passada fica registrada em `dados["revisoes"]` — o usuário vê o
    que a releitura acrescentou, e o custo fica somado na ficha.
    """
    ficha = (sessao_db.query(EditalFicha)
             .filter_by(licitacao_id=lic.id).first())
    if not (ficha and ficha.ficha_json):
        return analisar_edital(sessao_db, lic)
    cliente.exigir_chave()
    arquivos = (sessao_db.query(ArquivoEdital)
                .filter_by(licitacao_id=lic.id).all())
    texto, _ = extrair_texto_pdfs(arquivos)
    if not texto:
        ficha.erro = ("O pente fino precisa do texto do edital, e nem a "
                      "leitura por imagem encontrou texto legível.")
        sessao_db.commit()
        return ficha
    anterior = json.loads(ficha.ficha_json)
    revisoes = anterior.pop("revisoes", []) or []
    try:
        resposta = cliente.chamar(
            job="ficha_pente_fino",
            prompt_sistema=cliente.carregar_prompt("ficha-pente-fino"),
            mensagem=("FICHA DA PRIMEIRA LEITURA:\n"
                      + json.dumps(anterior, ensure_ascii=False, indent=1)
                      + "\n\n" + _mensagem(lic, texto)),
            modelo=camadas.PERICIA, max_tokens=16000, json_estrito=True)
        novo = json.loads(resposta)
        achados = novo.pop("achados_do_pente_fino", None) or []
        dados = _validar_ficha(json.dumps(novo, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — a ficha anterior continua valendo
        log.exception("Pente fino da licitação %s falhou", lic.id)
        ficha.erro = ("O pente fino não terminou desta vez. A ficha "
                      "anterior continua valendo.")
        sessao_db.commit()
        return ficha
    revisoes.append({"quando": agora().strftime("%d/%m/%Y %H:%M"),
                     "achados": [str(a) for a in achados][:40]})
    dados["revisoes"] = revisoes
    ficha.ficha_json = json.dumps(dados, ensure_ascii=False)
    ficha.erro = ""
    ficha.modelo = f"{ficha.modelo or camadas.EXTRACAO} + pente fino "
    ficha.modelo = ficha.modelo.replace(" + pente fino  + pente fino ",
                                        " + pente fino ").strip()
    ficha.versao_prompt = VERSAO_PROMPT_PENTE_FINO
    ficha.custo_usd = round((ficha.custo_usd or 0)
                            + _custo_da_ultima_chamada(), 4)
    ficha.gerada_em = agora()
    sessao_db.commit()
    log.info("Pente fino da licitação %s: %s achado(s), US$ %.4f",
             lic.id, len(achados), ficha.custo_usd)
    return ficha


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

    def _no_disco(lista):
        return [a for a in lista
                if a.caminho_local and os.path.exists(
                    os.path.join(PASTA_DADOS, a.caminho_local))]

    arquivos = (sessao_db.query(ArquivoEdital)
                .filter_by(licitacao_id=lic.id).all())
    if not _no_disco(arquivos):
        # Melhor esforço: busca os documentos agora, na hora do clique —
        # inclusive quando o banco tem linhas mas o arquivo saiu do disco.
        from .arquivos import baixar_arquivos
        try:
            baixar_arquivos(sessao_db, lic)
        except Exception:  # noqa: BLE001
            log.exception("Download na hora da análise falhou (lic %s)", lic.id)
        arquivos = (sessao_db.query(ArquivoEdital)
                    .filter_by(licitacao_id=lic.id).all())

    texto, lidos = extrair_texto_pdfs(arquivos)
    if not texto:
        ficha.erro = ("Não deu para ler o edital: "
                      + (_motivo_sem_texto(lic) if not _no_disco(arquivos)
                         else "nem a leitura por imagem encontrou texto "
                              "nos PDFs. Abra o documento pelo link e "
                              "confira se as páginas estão legíveis."))
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
