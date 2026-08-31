"""Wrapper único de chamadas a LLM (arquitetura §7).

TODA chamada de IA da plataforma passa por aqui — é o que garante, desde o
dia 1, saber quanto custa cada edital analisado e cada peça gerada. Nada de
chamada solta espalhada pelo código.

- Prompts vivem em `ia/prompts/*.md`, versionados; nunca inline.
- Saída estruturada é validada; retry limitado a 2.
- Custo de cada chamada vai para `data/ia_custos.jsonl` (uma linha por
  chamada: job, modelo, tokens, custo) — barato de agregar, impossível de
  perder de vista.
"""
import json
import logging
import os
import time

import requests

from app.config import PASTA_DADOS, agora

from . import camadas

log = logging.getLogger("licerta.ia")

RAIZ_IA = os.path.dirname(os.path.abspath(__file__))
CAMINHO_CUSTOS = os.path.join(PASTA_DADOS, "ia_custos.jsonl")
API_URL = "https://api.anthropic.com/v1/messages"
TENTATIVAS = 2


def carregar_prompt(nome):
    """Lê um prompt versionado de ia/prompts/ (ex.: 'analise-edital' ou
    'peritos/perito-contabil')."""
    caminho = os.path.join(RAIZ_IA, "prompts", f"{nome}.md")
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def _registrar_custo(job, modelo, tokens_entrada, tokens_saida, duracao_s):
    linha = {
        "quando": agora().isoformat(timespec="seconds"),
        "job": job, "modelo": modelo,
        "tokens_entrada": tokens_entrada, "tokens_saida": tokens_saida,
        "custo_usd": round(camadas.custo_usd(modelo, tokens_entrada,
                                             tokens_saida), 6),
        "duracao_s": round(duracao_s, 1),
    }
    try:
        with open(CAMINHO_CUSTOS, "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except OSError:  # registrar custo nunca derruba o job
        log.warning("Não consegui gravar o custo de IA em %s", CAMINHO_CUSTOS)
    return linha


def chamar(job, prompt_sistema, mensagem, modelo=None, max_tokens=4096,
           json_estrito=False):
    """Uma chamada de LLM com custo logado. Devolve o texto da resposta.

    `job` identifica quem chamou (ex.: 'analisar_edital') — é a chave do
    relatório de custo. `json_estrito=True` valida que a resposta é JSON e
    tenta de novo (até 2×) quando não é.
    """
    chave = os.environ.get("ANTHROPIC_API_KEY", "")
    if not chave:
        raise RuntimeError(
            "ANTHROPIC_API_KEY ausente no ambiente — os módulos de IA ficam "
            "desligados sem ela (o radar e os alertas seguem normais).")
    modelo = modelo or camadas.EXTRACAO
    ultima_falha = None
    for tentativa in range(1, TENTATIVAS + 1):
        inicio = time.monotonic()
        resposta = requests.post(API_URL, timeout=300, headers={
            "x-api-key": chave,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": modelo,
            "max_tokens": max_tokens,
            "system": prompt_sistema,
            "messages": [{"role": "user", "content": mensagem}],
        })
        if resposta.status_code == 429 or resposta.status_code >= 500:
            ultima_falha = f"API {resposta.status_code}"
            time.sleep(5 * tentativa)
            continue
        resposta.raise_for_status()
        dados = resposta.json()
        uso = dados.get("usage") or {}
        _registrar_custo(job, modelo, uso.get("input_tokens", 0),
                         uso.get("output_tokens", 0),
                         time.monotonic() - inicio)
        texto = "".join(b.get("text", "") for b in dados.get("content") or [])
        if not json_estrito:
            return texto
        try:
            json.loads(_extrair_json(texto))
            return _extrair_json(texto)
        except (ValueError, TypeError):
            ultima_falha = "resposta não é JSON válido"
            mensagem = (mensagem + "\n\nATENÇÃO: responda SOMENTE com o "
                        "JSON pedido, sem texto em volta.")
    raise RuntimeError(f"Chamada de IA '{job}' falhou após "
                       f"{TENTATIVAS} tentativas: {ultima_falha}")


def _extrair_json(texto):
    """Aceita a resposta com ou sem cerca de código em volta do JSON."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.split("```", 2)[1]
        texto = texto.split("\n", 1)[1] if texto.startswith("json") else texto
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio >= 0 and fim > inicio:
        return texto[inicio:fim + 1]
    return texto


def custo_total(job=None):
    """Soma o custo registrado (US$), opcionalmente de um job só."""
    total = 0.0
    try:
        with open(CAMINHO_CUSTOS, encoding="utf-8") as f:
            for linha in f:
                registro = json.loads(linha)
                if job is None or registro.get("job") == job:
                    total += registro.get("custo_usd", 0.0)
    except OSError:
        pass
    return round(total, 4)
