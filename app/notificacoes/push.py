"""Notificações push no celular/PC (Web Push), como as dos apps do governo.

O usuário aceita uma vez no aparelho e passa a receber o aviso na tela,
mesmo com o navegador fechado (Android; no iPhone exige o app "instalado"
pela opção Adicionar à Tela de Início). As chaves VAPID identificam esta
instalação e nascem sozinhas no primeiro uso, guardadas em data/ — fora do
código e fora do git, como a chave de sessão.
"""
import json
import logging
import os

from py_vapid import Vapid02, b64urlencode
from pywebpush import WebPushException, webpush

from ..config import PASTA_DADOS, config
from ..db import PushAssinatura

log = logging.getLogger("radar.push")

CAMINHO_CHAVE = os.path.join(PASTA_DADOS, "vapid_privada.pem")
_vapid = None


def _instancia():
    global _vapid
    if _vapid is None:
        try:
            _vapid = Vapid02.from_file(CAMINHO_CHAVE)  # cria e salva se faltar
        except Exception:  # noqa: BLE001 — sem escrita: chave só em memória
            log.warning("Sem escrita em %s; chave push vale até reiniciar "
                        "(os aparelhos precisarão ativar de novo)", CAMINHO_CHAVE)
            _vapid = Vapid02()
            _vapid.generate_keys()
    return _vapid


def chave_publica():
    """A chave que o navegador usa para assinar a adesão (base64url)."""
    v = _instancia()
    numeros = v.public_key.public_numbers()
    bruto = b"\x04" + numeros.x.to_bytes(32, "big") + numeros.y.to_bytes(32, "big")
    return b64urlencode(bruto)


def _claims(endpoint):
    email = config.EMAIL_DESTINO or "admin@radar.local"
    origem = "/".join(endpoint.split("/")[:3])
    return {"sub": f"mailto:{email}", "aud": origem}


def enviar_push(sessao_db, usuario, titulo, corpo, url="/"):
    """Manda a notificação a todos os aparelhos do usuário.

    Devolve quantos receberam. Aparelho que revogou a permissão (404/410)
    é removido na hora — senão a lista só cresce com endereços mortos.
    """
    assinaturas = (sessao_db.query(PushAssinatura)
                   .filter_by(usuario_id=usuario.id).all())
    entregues = 0
    for a in assinaturas:
        try:
            webpush(
                subscription_info={"endpoint": a.endpoint,
                                   "keys": {"p256dh": a.p256dh, "auth": a.auth}},
                data=json.dumps({"titulo": titulo, "corpo": corpo, "url": url},
                                ensure_ascii=False),
                vapid_private_key=_instancia().private_pem().decode(),
                vapid_claims=_claims(a.endpoint),
                ttl=6 * 3600, timeout=20)
            entregues += 1
        except WebPushException as e:
            codigo = getattr(getattr(e, "response", None), "status_code", None)
            if codigo in (404, 410):
                log.info("Aparelho saiu (%s); removendo a assinatura", codigo)
                sessao_db.delete(a)
            else:
                log.warning("Push falhou (%s): %s", codigo, e)
        except Exception as e:  # noqa: BLE001 — push nunca derruba um alerta
            log.warning("Push falhou: %s", e)
    sessao_db.commit()
    return entregues
