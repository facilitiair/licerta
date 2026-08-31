"""Contas de usuário: senha com scrypt salgado e sessão assinada.

Multiusuário: cada pessoa entra com o próprio e-mail e senha, tem os
próprios perfis e configura os próprios canais de aviso. A sessão é um
token 'id:validade:assinatura' — a assinatura usa a chave aleatória do
arquivo data/.segredo_sessao, então nada de segredo viaja no cookie.
"""
import base64
import hashlib
import hmac
import logging
import secrets
import time

from .db import Sessao, Usuario

log = logging.getLogger("radar.usuarios")

VALIDADE_SESSAO = 60 * 60 * 24 * 30      # 30 dias
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}  # equilíbrio custo × contêiner pequeno


def gerar_hash(senha):
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(senha.encode("utf-8"), salt=sal, **_SCRYPT)
    return "scrypt$" + base64.b64encode(sal).decode() + "$" + \
        base64.b64encode(derivada).decode()


def conferir_senha(senha, guardado):
    try:
        _, sal_b64, derivada_b64 = guardado.split("$")
        sal = base64.b64decode(sal_b64)
        esperada = base64.b64decode(derivada_b64)
        calculada = hashlib.scrypt(senha.encode("utf-8"), salt=sal, **_SCRYPT)
        return hmac.compare_digest(calculada, esperada)
    except (ValueError, TypeError):
        return False


def _assinatura(usuario_id, validade, segredo, senha_hash):
    # A senha entra na assinatura de propósito: trocar a senha derruba todas
    # as sessões daquele usuário (cookie roubado morre junto), sem derrubar
    # as sessões dos outros.
    corpo = f"{usuario_id}:{validade}:{senha_hash}"
    return hmac.new(segredo, corpo.encode(), hashlib.sha256).hexdigest()


def criar_token(usuario, segredo):
    validade = int(time.time()) + VALIDADE_SESSAO
    return (f"{usuario.id}:{validade}:"
            f"{_assinatura(usuario.id, validade, segredo, usuario.senha_hash)}")


def usuario_do_token(token, segredo):
    """Devolve o Usuario da sessão, ou None (token inválido, vencido, conta
    desativada ou senha trocada depois da emissão)."""
    try:
        uid, validade, assinatura = (token or "").split(":")
        if int(validade) < time.time():
            return None
        usuario = carregar_usuario(int(uid))
        if not usuario:
            return None
        esperada = _assinatura(usuario.id, validade, segredo,
                               usuario.senha_hash)
        return usuario if hmac.compare_digest(assinatura, esperada) else None
    except (ValueError, AttributeError):
        return None


def autenticar(email, senha):
    """Devolve o Usuario ativo que bate com as credenciais, ou None.

    Com o e-mail em branco, tenta a senha contra todos os usuários ativos —
    é o que deixa a instalação de uma pessoa só continuar entrando como
    sempre entrou, só com a senha.
    """
    sessao = Sessao()
    try:
        email = (email or "").strip().lower()
        if email:
            candidatos = sessao.query(Usuario).filter_by(
                email=email, ativo=True).all()
        else:
            candidatos = sessao.query(Usuario).filter_by(ativo=True).all()
        acertos = [u for u in candidatos if conferir_senha(senha, u.senha_hash)]
        if len(acertos) == 1:
            return acertos[0]
        if len(acertos) > 1:
            log.warning("Senha idêntica em mais de uma conta: exija o e-mail")
        return None
    finally:
        sessao.close()


def carregar_usuario(usuario_id):
    if not usuario_id:
        return None
    sessao = Sessao()
    try:
        u = sessao.get(Usuario, usuario_id)
        return u if (u and u.ativo) else None
    finally:
        sessao.close()
