"""Download automático dos PDFs de edital (Fase 3).

Baixa os documentos da API do PNCP para data/editais/<licitacao_id>/ e
registra em arquivos_edital. Melhor esforço: falha de um arquivo não
interrompe nada.

O acervo é CACHE com teto (EDITAIS_CACHE_MB): quando estoura, os PDFs
mais antigos saem primeiro. A URL de origem fica no banco, então o que
sair volta com um clique em "baixar documentos". Sem o teto, um dia de
coleta nacional encheu o volume inteiro do Railway.
"""
import logging
import os
import re

import requests

from ..config import PASTA_DADOS, config
from ..db import ArquivoEdital
from ..ingestao.pncp import listar_arquivos_compra

log = logging.getLogger("radar.documentos")

PASTA_EDITAIS = os.path.join(PASTA_DADOS, "editais")
MAX_ARQUIVOS_POR_LICITACAO = 5
MAX_TAMANHO = 60 * 1024 * 1024   # 60 MB por arquivo


def _sequencial(numero_controle):
    try:
        return int(numero_controle.split("-")[2].split("/")[0])
    except (ValueError, AttributeError, IndexError):
        return None


def _nome_seguro(texto, padrao):
    nome = re.sub(r"[^\w.\-]+", "_", texto or "").strip("_")
    return (nome or padrao)[:80]


def podar_cache(sessao_db, limite_mb=None):
    """Mantém o cache de PDFs dentro do teto, apagando os mais antigos.

    Roda no startup (o app se cura de um volume cheio ao subir) e após os
    downloads de cada coleta. Devolve (arquivos_apagados, mb_liberados).
    A linha em arquivos_edital sai junto do arquivo — linha apontando para
    arquivo inexistente é mentira no banco.
    """
    limite = (limite_mb if limite_mb is not None
              else config.EDITAIS_CACHE_MB) * 1024 * 1024
    encontrados = []
    total = 0
    for raiz, _, nomes in os.walk(PASTA_EDITAIS):
        for nome in nomes:
            caminho = os.path.join(raiz, nome)
            try:
                info = os.stat(caminho)
            except OSError:
                continue
            encontrados.append((info.st_mtime, info.st_size, caminho))
            total += info.st_size
    if total <= limite:
        return 0, 0
    apagados = liberados = 0
    for _, tamanho, caminho in sorted(encontrados):     # mais antigo primeiro
        if total - liberados <= limite:
            break
        try:
            os.remove(caminho)
        except OSError:
            continue
        liberados += tamanho
        apagados += 1
        relativo = os.path.relpath(caminho, PASTA_DADOS)
        sessao_db.query(ArquivoEdital).filter_by(
            caminho_local=relativo).delete(synchronize_session=False)
        # No Windows o caminho relativo grava com \; no Linux, com /.
        sessao_db.query(ArquivoEdital).filter_by(
            caminho_local=relativo.replace("\\", "/")).delete(
            synchronize_session=False)
        pasta = os.path.dirname(caminho)
        try:
            os.rmdir(pasta)                 # só sai se ficou vazia
        except OSError:
            pass
    sessao_db.commit()
    log.warning("Cache de editais podado: %s arquivos, %.0f MB liberados "
                "(teto %s MB)", apagados, liberados / 1e6,
                limite / 1024 / 1024)
    return apagados, liberados


def baixar_arquivos(sessao_db, lic, sessao=None):
    """Baixa os documentos de uma licitação do PNCP. Retorna qtd baixada."""
    if lic is None or lic.fonte != "pncp" or not (lic.orgao_cnpj and lic.ano_compra):
        return 0
    seq = _sequencial(lic.numero_controle_pncp)
    if not seq:
        return 0
    http = sessao or requests
    ja_baixados = {a.url_origem for a in
                   sessao_db.query(ArquivoEdital).filter_by(licitacao_id=lic.id)}
    docs = listar_arquivos_compra(lic.orgao_cnpj, lic.ano_compra, seq,
                                  sessao=sessao)
    pasta = os.path.join(PASTA_EDITAIS, str(lic.id))
    baixados = 0
    for doc in docs[:MAX_ARQUIVOS_POR_LICITACAO]:
        url = doc.get("url") or doc.get("uri")
        if not url or not doc.get("statusAtivo", True):
            continue
        # A API devolve URLs com portas internas (pncp.gov.br:51797) que não
        # aceitam conexão externa — o mesmo caminho funciona na porta padrão.
        url = re.sub(r"^(https://pncp\.gov\.br):\d+", r"\1", url)
        if url in ja_baixados:
            continue
        caminho = None
        try:
            resp = http.get(url, timeout=(10, 60), stream=True,
                            headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            os.makedirs(pasta, exist_ok=True)
            tipo = doc.get("tipoDocumentoNome") or "Documento"
            titulo = _nome_seguro(doc.get("titulo"),
                                  f"doc{doc.get('sequencialDocumento', 1)}")
            extensao = ".pdf" if "pdf" in resp.headers.get(
                "content-type", "").lower() else ""
            # Prefixo com o sequencial: dois documentos de mesmo título — caso
            # comum em edital retificado — gravavam no MESMO arquivo. O segundo
            # truncava o primeiro e as duas linhas do banco passavam a apontar
            # para o sobrevivente, sem erro nenhum.
            ordem = doc.get("sequencialDocumento") or (baixados + 1)
            caminho = os.path.join(pasta, f"{ordem}-{titulo}{extensao}")
            tamanho = 0
            with open(caminho, "wb") as f:
                for parte in resp.iter_content(1024 * 256):
                    tamanho += len(parte)
                    if tamanho > MAX_TAMANHO:
                        raise RuntimeError("arquivo maior que o limite")
                    f.write(parte)
            sessao_db.add(ArquivoEdital(
                licitacao_id=lic.id, titulo=doc.get("titulo") or titulo,
                tipo=tipo, url_origem=url,
                caminho_local=os.path.relpath(caminho, PASTA_DADOS)))
            baixados += 1
        except Exception as e:  # noqa: BLE001 — segue para o próximo arquivo
            log.warning("Falha ao baixar %s: %s", url, e)
    if baixados:
        sessao_db.commit()
    return baixados
