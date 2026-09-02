"""Sincroniza os perfis a partir do app publicado (a fonte da verdade).

O sistema roda em três lugares com três bancos: o app no Railway (Telegram),
o robô do GitHub Actions (e-mail, usa o banco do repositório) e o PC. Sem
isto, editar um perfil no site não mudava nada no robô do e-mail — os dois
divergiam em silêncio e cada canal alertava por critérios diferentes.

A direção é uma só: o site é onde se edita; os outros puxam de lá.
- Atualiza os perfis locais de mesmo nome e cria os que faltam.
- NUNCA apaga nem desativa um perfil que só existe localmente — ele apenas
  deixa de existir no site, e decisão de apagar é do dono.
- `ultimo_envio` não é copiado: é estado de cada instância, não configuração.

Uso: python -m app.sincronizar   (usa APP_URL e APP_SENHA do ambiente/.env)
"""
import logging

import requests

from .config import config
from .db import PerfilBusca, Sessao

log = logging.getLogger("radar.sincronizar")

# O que é configuração (viaja); id/criado_em/ultimo_envio ficam de fora.
CAMPOS = ["nome", "ativo", "ufs", "municipios_ibge", "modalidades",
          "palavras_incluir", "palavras_excluir", "valor_min", "valor_max",
          "somente_srp", "modo_busca", "ordenacao", "situacoes",
          "somente_vigentes", "notificar", "frequencia", "intervalo_horas",
          "dia_semana", "dia_mes", "mes_ano", "hora_envio"]

PERFIL_SISTEMA = "⭐ Salvos da pesquisa"


def exportar_perfis(sessao_db, usuario_id=None):
    """Os perfis como dicionários de configuração (para /api/perfis/exportar).

    Vai junto o e-mail do dono: no multiusuário, o robô do e-mail precisa
    saber de quem é cada perfil para avisar a pessoa certa. Com
    `usuario_id`, só os perfis daquela conta.
    """
    consulta = (sessao_db.query(PerfilBusca)
                .filter(PerfilBusca.nome != PERFIL_SISTEMA))
    if usuario_id is not None:
        consulta = consulta.filter(PerfilBusca.usuario_id == usuario_id)
    perfis = consulta.order_by(PerfilBusca.nome).all()
    resultado = []
    for p in perfis:
        d = {c: getattr(p, c) for c in CAMPOS}
        d["dono_email"] = p.usuario.email if p.usuario else ""
        resultado.append(d)
    return resultado


def _dono_local(sessao_db, dono_email):
    """O usuário local para pendurar o perfil sincronizado.

    Procura pelo e-mail; sem correspondência, cai no primeiro administrador —
    melhor um dono aproximado do que um perfil órfão que não alerta ninguém.
    """
    from .db import Usuario
    email = (dono_email or "").strip().lower()
    if email:
        u = sessao_db.query(Usuario).filter_by(email=email).first()
        if u:
            return u
    return (sessao_db.query(Usuario).filter_by(papel="admin")
            .order_by(Usuario.id).first())


def aplicar_perfis(sessao_db, recebidos):
    """Upsert por (dono, nome). Devolve (atualizados, criados). Sem commit."""
    atualizados, criados = [], []
    for dados in recebidos:
        nome = (dados.get("nome") or "").strip()
        if not nome or nome == PERFIL_SISTEMA:
            continue
        limpo = {c: dados[c] for c in CAMPOS if c in dados}
        dono = _dono_local(sessao_db, dados.get("dono_email"))
        consulta = sessao_db.query(PerfilBusca).filter_by(nome=nome)
        if dono:
            consulta = consulta.filter_by(usuario_id=dono.id)
        existente = consulta.first()
        if existente:
            mudou = False
            for campo, valor in limpo.items():
                if getattr(existente, campo) != valor:
                    setattr(existente, campo, valor)
                    mudou = True
            if mudou:
                atualizados.append(nome)
        else:
            sessao_db.add(PerfilBusca(
                **limpo, usuario_id=dono.id if dono else None))
            criados.append(nome)
    return atualizados, criados


def baixar_do_site(site=None, senha=None):
    """Busca os perfis do app publicado e aplica no banco local.

    Melhor esforço por natureza: sem endereço, sem senha ou com o site fora
    do ar, apenas avisa e devolve False — quem chama segue com o que tem.
    """
    site = (site or config.APP_URL or "").rstrip("/")
    senha = senha if senha is not None else config.APP_SENHA
    if not site or site.startswith("http://localhost"):
        log.info("Sincronização pulada: APP_URL não aponta para o site")
        return False
    try:
        s = requests.Session()
        if senha:
            s.post(f"{site}/login", data={"senha": senha},
                   allow_redirects=False, timeout=30)
        r = s.get(f"{site}/api/perfis/exportar", timeout=30,
                  allow_redirects=False)
        if r.status_code != 200:
            log.warning("Sincronização falhou: o site respondeu %s "
                        "(senha errada ou app antigo)", r.status_code)
            return False
        recebidos = r.json()
    except Exception as e:  # noqa: BLE001 — nunca derruba quem chamou
        log.warning("Sincronização falhou: %s", e)
        return False
    sessao_db = Sessao()
    try:
        atualizados, criados = aplicar_perfis(sessao_db, recebidos)
        sessao_db.commit()
        log.info("Perfis sincronizados do site: %s atualizados %s, "
                 "%s criados %s", len(atualizados), atualizados,
                 len(criados), criados)
        return True
    except Exception:  # noqa: BLE001
        sessao_db.rollback()
        log.exception("Erro ao aplicar os perfis sincronizados")
        return False
    finally:
        sessao_db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ok = baixar_do_site()
    print("Sincronização:", "ok" if ok else "não foi possível (veja acima)")
