"""Notificações push no celular/PC (Web Push), como as dos apps do governo.

O usuário aceita uma vez no aparelho e passa a receber o aviso na tela,
mesmo com o navegador fechado (Android; no iPhone exige o app "instalado"
pela opção Adicionar à Tela de Início). As chaves VAPID identificam esta
instalação e nascem sozinhas no primeiro uso, guardadas em data/ — fora do
código e fora do git, como a chave de sessão.

Cada aviso é UMA notificação nativa: título curto, texto com o que importa,
ícone do app, e ao tocar abre a página certa (não a raiz). A `tag` faz o
aparelho substituir um aviso antigo sobre o mesmo assunto em vez de
empilhar dois — o "prazo fechando" de um edital troca o "nova
oportunidade" dele, como um app de verdade faz.
"""
import json
import logging
import os
import re
import time

from py_vapid import Vapid02, b64urlencode
from pywebpush import WebPushException, webpush

from ..config import PASTA_DADOS, config
from ..db import PushAssinatura

log = logging.getLogger("radar.push")

CAMINHO_CHAVE = os.path.join(PASTA_DADOS, "vapid_privada.pem")

# Assuntos que o usuário pode ligar e desligar em Minha conta. A ordem é a
# da tela; a chave é o que fica gravado em usuarios.push_assuntos.
ASSUNTOS = [
    ("oportunidades", "Novas oportunidades dos meus perfis"),
    ("prazos", "Prazo fechando (antes do próximo alerta)"),
    ("alteracoes", "Edital que acompanho mudou"),
    ("dossie", "Certidão do dossiê vencendo"),
    ("sistema", "Saúde do sistema (só administradores)"),
]
ASSUNTOS_PADRAO = ",".join(chave for chave, _ in ASSUNTOS)
LIMITE_TITULO = 60          # Android corta o título perto disso
LIMITE_CORPO = 240          # expandido, o Android mostra até ~5 linhas
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


# O 'sub' do VAPID é um contato para o serviço de push; py_vapid recusa
# e-mail sem domínio com ponto ("x@y") e o envio morre sem chegar à rede.
_EMAIL_ACEITO = re.compile(r"^[^@\s]+@[\w%-]+(\.[\w%-]+)+$")
CONTATO_PADRAO = "admin@licerta.local"


def _claims(endpoint):
    email = (config.EMAIL_DESTINO or "").strip()
    if not _EMAIL_ACEITO.match(email):
        email = CONTATO_PADRAO
    origem = "/".join(endpoint.split("/")[:3])
    return {"sub": f"mailto:{email}", "aud": origem}


def preferencias(usuario):
    """As escolhas do usuário, com os padrões de fábrica para quem nunca
    mexeu (ou para objetos de teste sem essas colunas)."""
    assuntos = getattr(usuario, "push_assuntos", None)
    if assuntos is None:
        assuntos = ASSUNTOS_PADRAO
    return {
        "som": bool(getattr(usuario, "push_som", True)),
        "detalhado": bool(getattr(usuario, "push_detalhado", True)),
        "fixar_prazo": bool(getattr(usuario, "push_fixar_prazo", True)),
        "noturno": bool(getattr(usuario, "push_noturno", False)),
        "noturno_de": int(getattr(usuario, "push_noturno_de", 22) or 0),
        "noturno_ate": int(getattr(usuario, "push_noturno_ate", 7) or 0),
        "assuntos": {a.strip() for a in assuntos.split(",") if a.strip()},
    }


def quer_assunto(usuario, assunto):
    """O usuário deixou este assunto ligado? Sem assunto = aviso sempre
    (o teste de Minha conta, por exemplo)."""
    return assunto is None or assunto in preferencias(usuario)["assuntos"]


def em_silencio_noturno(prefs, hora=None):
    """Está dentro da faixa de silêncio? A faixa atravessa a meia-noite
    (22h→7h) ou não (13h→14h); as duas formas valem."""
    if not prefs["noturno"]:
        return False
    hora = config.agora().hour if hora is None else hora
    de, ate = prefs["noturno_de"], prefs["noturno_ate"]
    if de == ate:
        return False
    if de < ate:
        return de <= hora < ate
    return hora >= de or hora < ate


def montar_aviso(titulo, corpo, url="/", tag=None, urgente=False,
                 acao="Abrir", silencioso=False, fixar=None):
    """O pacote que o service worker transforma em notificação.

    Separado do envio para ser testável sem rede: é aqui que se garante
    título curto, corpo dentro do limite e o carimbo de hora (o aparelho
    mostra "há 5 min" a partir dele, como nos apps nativos).
    """
    titulo = (titulo or "Licerta").strip()
    if len(titulo) > LIMITE_TITULO:
        titulo = titulo[:LIMITE_TITULO - 1].rstrip() + "…"
    corpo = (corpo or "").strip()
    if len(corpo) > LIMITE_CORPO:
        corpo = corpo[:LIMITE_CORPO - 1].rstrip() + "…"
    return {
        "titulo": titulo,
        "corpo": corpo,
        "url": url or "/",
        "tag": tag or "licerta",
        "urgente": bool(urgente),
        "silencioso": bool(silencioso),
        "fixar": bool(urgente) if fixar is None else bool(fixar),
        "acao": acao,
        "quando": int(time.time() * 1000),
    }


def enviar_push(sessao_db, usuario, titulo, corpo, url="/", tag=None,
                urgente=False, acao="Abrir", assunto=None):
    """Manda a notificação a todos os aparelhos do usuário.

    Devolve quantos receberam. Aparelho que revogou a permissão (404/410)
    é removido na hora — senão a lista só cresce com endereços mortos.
    Respeita as preferências da pessoa: assunto desligado não sai; sem som
    (ou em silêncio noturno) chega mudo; prazo fechando fica fixo na tela
    até ela tocar, se assim quiser.
    """
    if not quer_assunto(usuario, assunto):
        return 0
    prefs = preferencias(usuario)
    silencioso = (not prefs["som"]) or em_silencio_noturno(prefs)
    fixar = bool(urgente) and prefs["fixar_prazo"]
    assinaturas = (sessao_db.query(PushAssinatura)
                   .filter_by(usuario_id=usuario.id).all())
    aviso = montar_aviso(titulo, corpo, url=url, tag=tag, urgente=urgente,
                         acao=acao, silencioso=silencioso, fixar=fixar)
    entregues = 0
    for a in assinaturas:
        try:
            webpush(
                subscription_info={"endpoint": a.endpoint,
                                   "keys": {"p256dh": a.p256dh, "auth": a.auth}},
                data=json.dumps(aviso, ensure_ascii=False),
                # O objeto Vapid, não o PEM: a pywebpush 2.x lê str como
                # chave crua em base64url e rejeitava o PEM ("Could not
                # deserialize key data") — nenhum aviso saía do servidor.
                vapid_private_key=_instancia(),
                vapid_claims=_claims(a.endpoint),
                # Urgente vale por um dia (o prazo é curto); o resto, três —
                # o celular desligado no fim de semana ainda recebe.
                ttl=(24 if urgente else 72) * 3600, timeout=20,
                headers={"Urgency": "high" if urgente else "normal"})
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
