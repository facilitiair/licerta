"""Leitura de PDF digitalizado — o modelo ENXERGA a página.

Um edital ou uma certidão escaneados não têm camada de texto: `pypdf`
devolve vazio e, até aqui, o analista desistia ("parece escaneado").
Aqui cada página vira imagem e o modelo de visão a transcreve, com regras
de fidelidade (ia/prompts/ocr-pagina.md). O texto resultante entra no
mesmo fluxo que o texto nativo: ficha, checklist, parecer, perícia,
tipo e validade do dossiê.

Custo e paciência:
- Cada página transcrita custa dinheiro; o resultado fica em cache ao
  lado do PDF (`<arquivo>.ocr.txt`) e nunca é pago duas vezes.
- Páginas vão em lotes de poucas imagens por chamada, com chamadas em
  paralelo, para o edital de 40 páginas caber no tempo de um clique.
- Tudo passa por `ia.cliente` — custo logado por job, como qualquer IA.
"""
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from . import camadas, cliente

log = logging.getLogger("licerta.ocr")

PAGINAS_POR_CHAMADA = 4
CHAMADAS_PARALELAS = 3
MAX_PAGINAS = 80          # teto por documento — edital maior lê o começo
DPI = 130                 # nítido para leitura, leve para o envio
MIN_CARACTERES_TEXTO = 200   # abaixo disso a camada de texto é ruído
SUFIXO_CACHE = ".ocr.txt"
MARCADOR = re.compile(r"^=== PÁGINA (\d+) ===\s*$", re.M)


def pdf_precisa_de_ocr(texto_nativo):
    """A camada de texto do PDF é inútil (escaneado, vazio, só ruído)?"""
    return len((texto_nativo or "").strip()) < MIN_CARACTERES_TEXTO


def _caminho_cache(caminho_pdf):
    return caminho_pdf + SUFIXO_CACHE


def renderizar_paginas(caminho_pdf, max_paginas=MAX_PAGINAS, dpi=DPI):
    """[(número, bytes JPEG)] das primeiras páginas do PDF."""
    import pymupdf
    imagens = []
    with pymupdf.open(caminho_pdf) as doc:
        for indice, pagina in enumerate(doc, start=1):
            if indice > max_paginas:
                break
            pix = pagina.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB,
                                    alpha=False)
            imagens.append((indice, pix.tobytes("jpeg", jpg_quality=80)))
    return imagens


def _transcrever_lote(lote, job):
    numeros = [n for n, _ in lote]
    mensagem = ("Transcreva as páginas a seguir. Numeração das imagens, na "
                "ordem: " + ", ".join(f"página {n}" for n in numeros) + ".")
    texto = cliente.chamar_visao(
        job=job, prompt_sistema=cliente.carregar_prompt("ocr-pagina"),
        imagens=[img for _, img in lote], mensagem=mensagem,
        modelo=camadas.OCR, max_tokens=16000)
    return _separar_paginas(texto, numeros)


def _separar_paginas(texto, numeros):
    """{número: texto} a partir da resposta com marcadores; resposta sem
    marcador cai inteira na primeira página do lote (nunca se perde)."""
    partes = MARCADOR.split(texto)
    if len(partes) < 3:
        return {numeros[0]: texto.strip()}
    paginas = {}
    for i in range(1, len(partes) - 1, 2):
        try:
            n = int(partes[i])
        except ValueError:
            continue
        paginas[n] = partes[i + 1].strip()
    return paginas


def transcrever_pdf(caminho_pdf, job="ocr", max_paginas=MAX_PAGINAS,
                    usar_cache=True):
    """Texto de um PDF digitalizado, página a página, com cache.

    Devolve '' quando a IA está desligada (sem chave) ou o PDF não abre —
    quem chama trata como "sem texto", exatamente como antes.
    """
    cache = _caminho_cache(caminho_pdf)
    if usar_cache and os.path.exists(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                return f.read()
        except OSError:
            pass
    try:
        cliente.exigir_chave()
    except cliente.SemChaveIA:
        log.info("OCR pulado (IA desligada): %s", caminho_pdf)
        return ""
    try:
        imagens = renderizar_paginas(caminho_pdf, max_paginas)
    except Exception as e:  # noqa: BLE001 — PDF corrompido não derruba nada
        log.warning("Não renderizei %s para OCR: %s", caminho_pdf, e)
        return ""
    if not imagens:
        return ""
    lotes = [imagens[i:i + PAGINAS_POR_CHAMADA]
             for i in range(0, len(imagens), PAGINAS_POR_CHAMADA)]
    paginas = {}
    with ThreadPoolExecutor(max_workers=CHAMADAS_PARALELAS) as executor:
        for resultado in executor.map(
                lambda lote: _transcrever_lote(lote, job), lotes):
            paginas.update(resultado)
    texto = "\n\n".join(f"=== PÁGINA {n} ===\n{paginas[n]}"
                        for n in sorted(paginas))
    if texto.strip():
        try:
            with open(cache, "w", encoding="utf-8") as f:
                f.write(texto)
        except OSError:
            log.warning("Não gravei o cache de OCR em %s", cache)
    log.info("OCR de %s: %s páginas, %s caracteres", caminho_pdf,
             len(paginas), len(texto))
    return texto


def texto_do_pdf(caminho_pdf, max_paginas=MAX_PAGINAS, job="ocr",
                 max_paginas_nativo=None):
    """Texto de um PDF por qualquer caminho: camada nativa ou, se ela não
    existe, transcrição por visão. Devolve (texto, veio_de_ocr)."""
    from pypdf import PdfReader
    nativo = ""
    try:
        paginas = PdfReader(caminho_pdf).pages
        if max_paginas_nativo:
            paginas = paginas[:max_paginas_nativo]
        nativo = "\n".join((p.extract_text() or "") for p in paginas)
    except Exception as e:  # noqa: BLE001
        log.warning("pypdf não leu %s: %s", caminho_pdf, e)
    if not pdf_precisa_de_ocr(nativo):
        return nativo, False
    return transcrever_pdf(caminho_pdf, job=job, max_paginas=max_paginas), True
