"""Radar de Licitações — servidor web (FastAPI) + agendador (APScheduler).

Subir com:  uvicorn app.main:app  (ou  python -m app.main)
"""
import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import alerta as alerta_mod
from .coleta import coleta_em_andamento, coletar_em_background
from .config import config
from .db import (ColetaLog, Licitacao, Modalidade, Municipio, PerfilBusca,
                 PerfilMatch, Sessao, criar_tabelas)
from .matcher import licitacao_casa_perfil
from .seed import semear

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("radar")

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates"))

agendador = BackgroundScheduler(timezone=config.TZ)


def _job_coleta():
    """Job diário de coleta. Roda em thread própria; nunca derruba o agendador."""
    try:
        from .coleta import coletar
        coletar()
    except Exception:  # noqa: BLE001
        log.exception("Erro no job de coleta")


def _job_alerta():
    try:
        alerta_mod.enviar_alerta_diario()
    except Exception:  # noqa: BLE001
        log.exception("Erro no job de alerta")


@asynccontextmanager
async def vida(app_):
    criar_tabelas()
    semear()
    h, m = config.HORA_COLETA
    agendador.add_job(_job_coleta, "cron", hour=h, minute=m, id="coleta")
    h, m = config.HORA_ALERTA
    agendador.add_job(_job_alerta, "cron", hour=h, minute=m, id="alerta")
    agendador.start()
    log.info("Agendador ativo: coleta %02d:%02d, alerta %02d:%02d (%s)",
             *config.HORA_COLETA, *config.HORA_ALERTA, config.TZ)
    yield
    agendador.shutdown(wait=False)


app = FastAPI(title="Radar de Licitações", lifespan=vida)


# ---------------------------------------------------------------- autenticação
def _token_sessao():
    return hmac.new(b"radar-licitacoes",
                    config.APP_SENHA.encode(), hashlib.sha256).hexdigest()


def logado(request: Request):
    """Sem APP_SENHA no .env o painel fica aberto (uso em rede local)."""
    if not config.APP_SENHA:
        return True
    return hmac.compare_digest(request.cookies.get("sessao", ""), _token_sessao())


@app.middleware("http")
async def exigir_login(request: Request, call_next):
    livre = request.url.path in ("/login",) or request.url.path.startswith("/static")
    if not livre and not logado(request):
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erro": None})


@app.post("/login")
async def login(request: Request, senha: str = Form("")):
    if hmac.compare_digest(senha, config.APP_SENHA):
        resposta = RedirectResponse("/", status_code=303)
        resposta.set_cookie("sessao", _token_sessao(), httponly=True,
                            max_age=60 * 60 * 24 * 30)
        return resposta
    return templates.TemplateResponse(request, "login.html",
                                      {"erro": "Senha incorreta."})


@app.get("/logout")
async def logout():
    resposta = RedirectResponse("/login", status_code=303)
    resposta.delete_cookie("sessao")
    return resposta


# --------------------------------------------------------------------- painel
@app.get("/", response_class=HTMLResponse)
async def painel(request: Request):
    s = Sessao()
    try:
        perfis = s.query(PerfilBusca).order_by(PerfilBusca.nome).all()
        cartoes = []
        for p in perfis:
            novos = (s.query(PerfilMatch)
                     .filter_by(perfil_id=p.id, lido=False).count())
            total = s.query(PerfilMatch).filter_by(perfil_id=p.id).count()
            cartoes.append({"perfil": p, "novos": novos, "total": total})
        ultima = (s.query(ColetaLog).filter_by(sucesso=True)
                  .order_by(ColetaLog.fim.desc()).first())
        ultimas20 = (s.query(Licitacao)
                     .order_by(Licitacao.coletado_em.desc()).limit(20).all())
        return templates.TemplateResponse(request, "painel.html", {
            "cartoes": cartoes, "ultima_coleta": ultima,
            "ultimas": ultimas20, "coletando": coleta_em_andamento(),
        })
    finally:
        s.close()


@app.post("/coletar", response_class=HTMLResponse)
async def coletar_agora(request: Request):
    if not coleta_em_andamento():
        coletar_em_background()
    return templates.TemplateResponse(request, "_coleta_status.html",
                                      {"coletando": True})


@app.get("/coleta/status", response_class=HTMLResponse)
async def coleta_status(request: Request):
    return templates.TemplateResponse(request, "_coleta_status.html",
                                      {"coletando": coleta_em_andamento()})


# --------------------------------------------------------------------- perfis
def _form_para_perfil(form):
    """Converte o formulário HTML nos campos JSON da tabela perfis_busca."""
    def linhas(nome):
        return [t.strip() for t in form.get(nome, "").splitlines() if t.strip()]

    def numero(nome):
        bruto = (form.get(nome) or "").replace(".", "").replace(",", ".").strip()
        return float(bruto) if bruto else None

    return {
        "nome": form.get("nome", "").strip() or "Sem nome",
        "ativo": form.get("ativo") == "on",
        "ufs": form.getlist("ufs"),
        "municipios_ibge": [m for m in form.getlist("municipios_ibge") if m],
        "modalidades": [int(m) for m in form.getlist("modalidades")],
        "palavras_incluir": linhas("palavras_incluir"),
        "palavras_excluir": linhas("palavras_excluir"),
        "valor_min": numero("valor_min"),
        "valor_max": numero("valor_max"),
        "somente_srp": form.get("somente_srp") == "on",
        "ordenacao": form.get("ordenacao", "encerramento_asc"),
        "notificar": form.get("notificar") == "on",
    }


def _contexto_form(request, s, perfil):
    municipios_sel = []
    if perfil and perfil.municipios_ibge:
        municipios_sel = (s.query(Municipio).filter(
            Municipio.codigo_ibge.in_([str(m) for m in perfil.municipios_ibge]))
            .all())
    return {"perfil": perfil,
            "modalidades": s.query(Modalidade).order_by(Modalidade.codigo).all(),
            "municipios_sel": municipios_sel,
            "ufs_todas": ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
                          "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
                          "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]}


@app.get("/perfis", response_class=HTMLResponse)
async def perfis_lista(request: Request):
    s = Sessao()
    try:
        perfis = s.query(PerfilBusca).order_by(PerfilBusca.nome).all()
        return templates.TemplateResponse(request, "perfis.html",
                                          {"perfis": perfis})
    finally:
        s.close()


@app.get("/perfis/novo", response_class=HTMLResponse)
async def perfil_novo(request: Request):
    s = Sessao()
    try:
        return templates.TemplateResponse(request, "perfil_form.html",
                                          _contexto_form(request, s, None))
    finally:
        s.close()


@app.get("/perfis/{perfil_id}", response_class=HTMLResponse)
async def perfil_editar(request: Request, perfil_id: int):
    s = Sessao()
    try:
        perfil = s.get(PerfilBusca, perfil_id)
        if not perfil:
            return RedirectResponse("/perfis", status_code=303)
        return templates.TemplateResponse(request, "perfil_form.html",
                                          _contexto_form(request, s, perfil))
    finally:
        s.close()


@app.post("/perfis/salvar")
async def perfil_salvar(request: Request):
    form = await request.form()
    dados = _form_para_perfil(form)
    s = Sessao()
    try:
        perfil_id = form.get("perfil_id")
        if perfil_id:
            perfil = s.get(PerfilBusca, int(perfil_id))
            for campo, valor in dados.items():
                setattr(perfil, campo, valor)
        else:
            s.add(PerfilBusca(**dados))
        s.commit()
        return RedirectResponse("/perfis", status_code=303)
    finally:
        s.close()


@app.post("/perfis/preview", response_class=HTMLResponse)
async def perfil_preview(request: Request):
    """Roda o matcher contra o banco atual sem salvar (SPEC §7)."""
    form = await request.form()
    dados = _form_para_perfil(form)
    rascunho = PerfilBusca(**dados)
    s = Sessao()
    try:
        total = sum(1 for lic in s.query(Licitacao).all()
                    if licitacao_casa_perfil(lic, rascunho))
        return HTMLResponse(
            f'<span class="text-blue-700 font-semibold">{total} licitação(ões) '
            'já gravadas no banco casariam com este perfil.</span>')
    finally:
        s.close()


@app.post("/perfis/{perfil_id}/toggle")
async def perfil_toggle(perfil_id: int):
    s = Sessao()
    try:
        perfil = s.get(PerfilBusca, perfil_id)
        if perfil:
            perfil.ativo = not perfil.ativo
            s.commit()
        return RedirectResponse("/perfis", status_code=303)
    finally:
        s.close()


@app.post("/perfis/{perfil_id}/duplicar")
async def perfil_duplicar(perfil_id: int):
    s = Sessao()
    try:
        original = s.get(PerfilBusca, perfil_id)
        if original:
            s.add(PerfilBusca(
                nome=f"{original.nome} (cópia)", ativo=False,
                ufs=list(original.ufs or []),
                municipios_ibge=list(original.municipios_ibge or []),
                modalidades=list(original.modalidades or []),
                palavras_incluir=list(original.palavras_incluir or []),
                palavras_excluir=list(original.palavras_excluir or []),
                valor_min=original.valor_min, valor_max=original.valor_max,
                somente_srp=original.somente_srp, ordenacao=original.ordenacao,
                notificar=original.notificar))
            s.commit()
        return RedirectResponse("/perfis", status_code=303)
    finally:
        s.close()


@app.post("/perfis/{perfil_id}/excluir")
async def perfil_excluir(perfil_id: int):
    s = Sessao()
    try:
        perfil = s.get(PerfilBusca, perfil_id)
        if perfil:
            s.delete(perfil)
            s.commit()
        return RedirectResponse("/perfis", status_code=303)
    finally:
        s.close()


@app.get("/api/municipios", response_class=HTMLResponse)
async def municipios_busca(request: Request, uf: str = "", q: str = ""):
    """Busca por digitação para o seletor de municípios (HTMX)."""
    if len(q) < 2:
        return HTMLResponse("")
    s = Sessao()
    try:
        consulta = s.query(Municipio).filter(Municipio.nome.ilike(f"%{q}%"))
        if uf:
            consulta = consulta.filter(Municipio.uf.in_(uf.split(",")))
        municipios = consulta.order_by(Municipio.nome).limit(12).all()
        return templates.TemplateResponse(request, "_municipios_busca.html",
                                          {"municipios": municipios})
    finally:
        s.close()


# ------------------------------------------------------------------- execução
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
