"""Radar de Licitações — servidor web (FastAPI) + agendador (APScheduler).

Subir com:  uvicorn app.main:app  (ou  python -m app.main)
"""
import hashlib
import hmac
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from urllib.parse import urlencode

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, RedirectResponse,
                               Response)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import alerta as alerta_mod
from . import envcfg
from . import pncp_busca
from .coleta import coleta_em_andamento, coletar_em_background
from .config import PASTA_DADOS, agora, config
from .db import (ArquivoEdital, Ata, ColetaLog, Licitacao, Modalidade,
                 Municipio, PerfilBusca, PerfilMatch, Sessao, criar_tabelas)
from .documentos import baixar_arquivos
from .exportar import gerar_csv, gerar_xlsx
from .matcher import (SITUACOES_CONHECIDAS, SITUACOES_DISPUTAVEIS,
                      licitacao_casa_perfil, normalizar)
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


def _gatilho_coleta():
    """Horas em que a coleta roda: a partir da HORA_COLETA, de N em N horas.

    Com N=24 vira a coleta única de sempre; com N=3 o banco fica fresco o dia
    todo, que é o que impede um edital das 9h de só ser visto amanhã.
    """
    h, m = config.HORA_COLETA
    passo = config.HORAS_ENTRE_COLETAS
    horas = sorted({(h + i * passo) % 24 for i in range(24 // passo or 1)})
    return {"hour": ",".join(str(x) for x in horas), "minute": m}


def _job_alerta():
    """Roda de 10 em 10 minutos e envia os alertas cuja hora chegou.

    Varrer com frequência (em vez de um job por perfil) mantém um caminho só:
    mudar a frequência de um alerta na tela não exige reagendar nada."""
    try:
        alerta_mod.enviar_alertas_devidos()
    except Exception:  # noqa: BLE001
        log.exception("Erro no job de alerta")


@asynccontextmanager
async def vida(app_):
    criar_tabelas()
    semear()
    # Coletas que ficaram "em andamento" (processo reiniciado no meio) são fechadas
    s = Sessao()
    try:
        s.query(ColetaLog).filter(ColetaLog.fim.is_(None)).update(
            {"fim": agora(), "sucesso": False,
             "detalhe_erro": "coleta interrompida por reinício do aplicativo"})
        s.commit()
    finally:
        s.close()
    agendador.add_job(_job_coleta, "cron", id="coleta", replace_existing=True,
                      **_gatilho_coleta())
    agendador.add_job(_job_alerta, "interval", minutes=10, id="alerta",
                      replace_existing=True)
    if not agendador.running:
        agendador.start()
    log.info("Agendador ativo: coleta às %sh; alertas conferidos a cada "
             "10 min, cada um na sua frequência (%s)",
             _gatilho_coleta()["hour"], config.TZ)
    yield
    if agendador.running:
        agendador.shutdown(wait=False)


app = FastAPI(title="Radar de Licitações", lifespan=vida)
app.mount("/static", StaticFiles(
    directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


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


# ------------------------------------------------------------------ dashboard
def _dias_ate(data_iso):
    try:
        alvo = datetime.strptime(data_iso[:10], "%Y-%m-%d")
        return (alvo - agora()).days + 1
    except (ValueError, TypeError):
        return None


@app.get("/", response_class=HTMLResponse)
async def painel(request: Request):
    s = Sessao()
    try:
        def conta(status):
            return s.query(PerfilMatch).filter_by(status=status).count()

        hoje = agora().strftime("%Y-%m-%d")
        ativos = (s.query(PerfilMatch).join(Licitacao)
                  .filter(PerfilMatch.status != "descartado",
                          Licitacao.data_encerramento_proposta >= hoje)
                  .order_by(Licitacao.data_encerramento_proposta))
        urgentes = [m for m in ativos
                    if (_dias_ate(m.licitacao.data_encerramento_proposta) or 99) <= 7]
        proximos = [{"lic": m.licitacao, "status": m.status,
                     "dias": _dias_ate(m.licitacao.data_encerramento_proposta)}
                    for m in ativos.limit(8)]
        kpis = {"novas": conta("novo"), "analisando": conta("analisando"),
                "participar": conta("vou_participar"), "urgentes": len(urgentes)}
        ultima = (s.query(ColetaLog).filter_by(sucesso=True)
                  .order_by(ColetaLog.fim.desc()).first())
        ultimas = (s.query(Licitacao)
                   .order_by(Licitacao.coletado_em.desc()).limit(8).all())
        return templates.TemplateResponse(request, "painel.html", {
            "kpis": kpis, "proximos": proximos, "ultima_coleta": ultima,
            "ultimas": ultimas, "coletando": coleta_em_andamento(),
            "hora_coleta": config.HORA_COLETA,
        })
    finally:
        s.close()


# ---------------------------------------------------------- funil (kanban)
COLUNAS_FUNIL = [("novo", "🟡 Novas"), ("analisando", "🔵 Em análise"),
                 ("vou_participar", "🟢 Vou participar"),
                 ("descartado", "⚪ Descartadas")]


def _contexto_funil(s):
    hoje = agora().strftime("%Y-%m-%d")
    colunas = []
    for status, rotulo in COLUNAS_FUNIL:
        consulta = (s.query(PerfilMatch).join(Licitacao)
                    .filter(PerfilMatch.status == status)
                    .order_by(Licitacao.data_encerramento_proposta))
        if status != "descartado":     # descartadas antigas não interessam
            consulta = consulta.filter(
                Licitacao.data_encerramento_proposta >= hoje)
        matches = consulta.limit(40).all()
        cartoes = [{"m": m, "dias": _dias_ate(
            m.licitacao.data_encerramento_proposta)} for m in matches]
        colunas.append({"status": status, "rotulo": rotulo, "cartoes": cartoes})
    return {"colunas": colunas}


@app.get("/funil", response_class=HTMLResponse)
async def funil(request: Request):
    s = Sessao()
    try:
        return templates.TemplateResponse(request, "funil.html",
                                          _contexto_funil(s))
    finally:
        s.close()


@app.post("/funil/mover/{match_id}/{status}", response_class=HTMLResponse)
async def funil_mover(request: Request, match_id: int, status: str):
    s = Sessao()
    try:
        m = s.get(PerfilMatch, match_id)
        if m and status in ("novo", "analisando", "vou_participar", "descartado"):
            m.status = status
            m.lido = True
            s.commit()
        return templates.TemplateResponse(request, "_funil_board.html",
                                          _contexto_funil(s))
    finally:
        s.close()


# --------------------------------------------------------------------- agenda
@app.get("/agenda", response_class=HTMLResponse)
async def agenda(request: Request):
    s = Sessao()
    try:
        hoje = agora().strftime("%Y-%m-%d")
        matches = (s.query(PerfilMatch).join(Licitacao)
                   .filter(PerfilMatch.status != "descartado",
                           Licitacao.data_encerramento_proposta >= hoje)
                   .order_by(Licitacao.data_encerramento_proposta).all())
        dias = {}
        for m in matches:
            chave = m.licitacao.data_encerramento_proposta[:10]
            dias.setdefault(chave, []).append(m)
        semana = ["segunda", "terça", "quarta", "quinta", "sexta",
                  "sábado", "domingo"]
        agenda_dias = []
        for d, ms in dias.items():
            dt = datetime.strptime(d, "%Y-%m-%d")
            agenda_dias.append({
                "data": d,
                "rotulo": f"{dt.strftime('%d/%m/%Y')} ({semana[dt.weekday()]})",
                "dias_ate": _dias_ate(d), "matches": ms})
        return templates.TemplateResponse(request, "agenda.html",
                                          {"agenda_dias": agenda_dias})
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
_HORA_VALIDA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _form_para_perfil(form):
    """Converte o formulário HTML nos campos JSON da tabela perfis_busca."""
    def linhas(nome):
        return [t.strip() for t in form.get(nome, "").splitlines() if t.strip()]

    def numero(nome):
        bruto = (form.get(nome) or "").replace(".", "").replace(",", ".").strip()
        try:
            return float(bruto) if bruto else None
        except ValueError:
            return None            # texto inválido no campo de valor: ignora

    def inteiro(nome, padrao, minimo, maximo):
        try:
            return max(minimo, min(maximo, int(form.get(nome) or padrao)))
        except (TypeError, ValueError):
            return padrao

    hora = (form.get("hora_envio") or "").strip()
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
        "modo_busca": form.get("modo_busca", "ou"),
        "ordenacao": form.get("ordenacao", "encerramento_asc"),
        "situacoes": form.getlist("situacoes"),
        "somente_vigentes": form.get("somente_vigentes") == "on",
        "notificar": form.get("notificar") == "on",
        "frequencia": (form.get("frequencia") if form.get("frequencia")
                       in alerta_mod.FREQUENCIAS else "diario"),
        "intervalo_horas": inteiro("intervalo_horas", 3, 1, 12),
        "dia_semana": inteiro("dia_semana", 0, 0, 6),
        "dia_mes": inteiro("dia_mes", 1, 1, 28),
        "mes_ano": inteiro("mes_ano", 1, 1, 12),
        "hora_envio": hora if _HORA_VALIDA.match(hora) else "",
    }


def _situacoes_disponiveis(s):
    """As situações conhecidas mais as que realmente apareceram na coleta —
    assim a tela nunca fica sem uma opção que existe no banco."""
    vistas = [linha[0] for linha in
              s.query(Licitacao.situacao).distinct() if linha[0]]
    return SITUACOES_CONHECIDAS + sorted(
        v for v in set(vistas) if v not in SITUACOES_CONHECIDAS)


def _contexto_form(request, s, perfil):
    municipios_sel = []
    if perfil and perfil.municipios_ibge:
        municipios_sel = (s.query(Municipio).filter(
            Municipio.codigo_ibge.in_([str(m) for m in perfil.municipios_ibge]))
            .all())
    return {"perfil": perfil,
            "modalidades": s.query(Modalidade).order_by(Modalidade.codigo).all(),
            "municipios_sel": municipios_sel,
            "situacoes_todas": _situacoes_disponiveis(s),
            "situacoes_padrao": SITUACOES_DISPUTAVEIS,
            "frequencias": alerta_mod.FREQUENCIAS,
            "dias_semana": alerta_mod.DIAS_SEMANA,
            "meses": alerta_mod.MESES,
            "hora_padrao": "%02d:%02d" % config.HORA_ALERTA,
            "ufs_todas": ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
                          "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
                          "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]}


@app.get("/perfis", response_class=HTMLResponse)
async def perfis_lista(request: Request):
    s = Sessao()
    try:
        perfis = s.query(PerfilBusca).order_by(PerfilBusca.nome).all()
        return templates.TemplateResponse(request, "perfis.html", {
            "perfis": perfis, "resumo_frequencia": alerta_mod.resumo_frequencia,
            "enviado": request.query_params.get("enviado")})
    finally:
        s.close()


@app.get("/perfis/novo", response_class=HTMLResponse)
async def perfil_novo(request: Request):
    s = Sessao()
    try:
        contexto = _contexto_form(request, s, None)
        qp = request.query_params
        if qp.get("q") or qp.getlist("ufs"):
            # veio do botão "criar perfil desta busca" da pesquisa ao vivo
            palavras = [t.strip() for t in qp.get("q", "").split(",")
                        if t.strip()] or ([qp.get("q")] if qp.get("q") else [])
            contexto["perfil"] = PerfilBusca(
                nome=f"Busca: {qp.get('q', 'nova')}"[:60],
                ufs=qp.getlist("ufs"),
                modalidades=[int(m) for m in qp.getlist("modalidades")
                             if m.isdigit()],
                municipios_ibge=[], palavras_incluir=palavras,
                palavras_excluir=[], somente_srp=False, modo_busca="e",
                ordenacao="encerramento_asc", ativo=True, notificar=True,
                situacoes=list(SITUACOES_DISPUTAVEIS), somente_vigentes=True,
                frequencia="diario", intervalo_horas=3, dia_semana=0,
                dia_mes=1, mes_ano=1, hora_envio="")
        return templates.TemplateResponse(request, "perfil_form.html", contexto)
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
        perfil_id = form.get("perfil_id", "")
        perfil = s.get(PerfilBusca, int(perfil_id)) if perfil_id.isdigit() else None
        if perfil:
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
                modo_busca=original.modo_busca,
                situacoes=list(original.situacoes or []),
                somente_vigentes=original.somente_vigentes,
                notificar=original.notificar, frequencia=original.frequencia,
                intervalo_horas=original.intervalo_horas,
                dia_semana=original.dia_semana, dia_mes=original.dia_mes,
                mes_ano=original.mes_ano, hora_envio=original.hora_envio))
            s.commit()
        return RedirectResponse("/perfis", status_code=303)
    finally:
        s.close()


@app.post("/perfis/{perfil_id}/enviar")
async def perfil_enviar_agora(perfil_id: int):
    """Botão 'Enviar agora': dispara este alerta fora da agenda."""
    enviados = alerta_mod.enviar_alertas_devidos(perfil_id=perfil_id)
    return RedirectResponse(f"/perfis?enviado={'sim' if enviados else 'vazio'}",
                            status_code=303)


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


# ----------------------------------------------------------------- licitações
def _ordenacoes_lista():
    """Ordenações da tabela: cada opção é uma lista de colunas (com desempate)."""
    from sqlalchemy import nullslast
    enc, pub = Licitacao.data_encerramento_proposta, Licitacao.data_publicacao_pncp
    val, uf = Licitacao.valor_total_estimado, Licitacao.uf
    mun, mod = Licitacao.municipio_nome, Licitacao.modalidade_nome
    sit, org = Licitacao.situacao, Licitacao.orgao_nome
    return {
        "encerramento_asc": [nullslast(enc.asc())],
        "encerramento_desc": [enc.desc()],
        "publicacao_desc": [pub.desc()],
        "publicacao_asc": [pub.asc()],
        "valor_asc": [nullslast(val.asc())],
        "valor_desc": [nullslast(val.desc())],
        "uf_asc": [uf.asc(), nullslast(enc.asc())],
        "uf_desc": [uf.desc(), nullslast(enc.asc())],
        "municipio_asc": [mun.asc(), nullslast(enc.asc())],
        "municipio_desc": [mun.desc(), nullslast(enc.asc())],
        "orgao_asc": [org.asc()],
        "modalidade_asc": [mod.asc(), nullslast(enc.asc())],
        "modalidade_desc": [mod.desc(), nullslast(enc.asc())],
        "situacao_asc": [sit.asc(), nullslast(enc.asc())],
        "objeto_asc": [Licitacao.objeto_norm.asc()],
    }


ORDENACAO_PADRAO = "uf_asc"     # todos os estados: lista em ordem alfabética
POR_PAGINA = 50


def _consulta_licitacoes(s, filtros):
    """Monta a consulta a partir dos filtros da tela (também usada na exportação)."""
    consulta = s.query(Licitacao)
    # entradas numéricas vindas da URL: ignora silenciosamente o que não for número
    for campo in ("perfil_id", "modalidade"):
        if filtros.get(campo) and not str(filtros[campo]).isdigit():
            filtros[campo] = ""
    if filtros.get("perfil_id"):
        consulta = consulta.join(
            PerfilMatch, (PerfilMatch.licitacao_id == Licitacao.id) &
                         (PerfilMatch.perfil_id == int(filtros["perfil_id"])))
        if filtros.get("status"):
            consulta = consulta.filter(PerfilMatch.status == filtros["status"])
    elif filtros.get("status"):
        consulta = (consulta.join(PerfilMatch,
                                  PerfilMatch.licitacao_id == Licitacao.id)
                    .filter(PerfilMatch.status == filtros["status"]).distinct())
    if filtros.get("uf"):
        consulta = consulta.filter(Licitacao.uf == filtros["uf"])
    if filtros.get("municipio"):
        consulta = consulta.filter(
            Licitacao.municipio_nome.ilike(f"%{filtros['municipio']}%"))
    if filtros.get("modalidade"):
        consulta = consulta.filter(
            Licitacao.modalidade_codigo == int(filtros["modalidade"]))
    if filtros.get("situacao"):
        consulta = consulta.filter(Licitacao.situacao == filtros["situacao"])
    if filtros.get("data_ini"):
        consulta = consulta.filter(
            Licitacao.data_encerramento_proposta >= filtros["data_ini"])
    if filtros.get("data_fim"):
        consulta = consulta.filter(
            Licitacao.data_encerramento_proposta <= filtros["data_fim"] + "T23:59")
    if filtros.get("q"):
        # busca sem acentos, palavra a palavra: TODAS precisam aparecer
        for palavra in normalizar(filtros["q"]).split():
            consulta = consulta.filter(
                Licitacao.objeto_norm.like(f"%{palavra}%"))
    ordens = _ordenacoes_lista()
    colunas = ordens.get(filtros.get("ordenar") or "", ordens[ORDENACAO_PADRAO])
    return consulta.order_by(*colunas)


def _filtros_da_request(request):
    campos = ("perfil_id", "status", "uf", "municipio", "modalidade",
              "situacao", "data_ini", "data_fim", "q", "ordenar")
    return {c: request.query_params.get(c, "").strip() for c in campos}


@app.get("/licitacoes", response_class=HTMLResponse)
async def licitacoes_lista(request: Request, pagina: int = 1):
    pagina = max(1, pagina)
    s = Sessao()
    try:
        filtros = _filtros_da_request(request)
        consulta = _consulta_licitacoes(s, filtros)
        total = consulta.count()
        linhas = consulta.offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all()
        # Status/favorito por licitação, para as badges (quando há perfil filtrado)
        matches = {}
        if filtros["perfil_id"]:
            for m in s.query(PerfilMatch).filter_by(
                    perfil_id=int(filtros["perfil_id"])):
                matches[m.licitacao_id] = m
        perfis = s.query(PerfilBusca).order_by(PerfilBusca.nome).all()
        ufs = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
               "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
               "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
        modalidades = s.query(Modalidade).order_by(Modalidade.codigo).all()
        situacoes = [x[0] for x in s.query(Licitacao.situacao).distinct()
                     .order_by(Licitacao.situacao) if x[0]]
        # Radar vazio para esses filtros? Busca AO VIVO no PNCP com os mesmos
        # critérios e entrega os resultados na própria tela.
        vivo, vivo_total = [], 0
        if total == 0 and any(filtros.get(c) for c in
                              ("q", "uf", "municipio", "modalidade")):
            try:
                muns = []
                if filtros.get("municipio"):
                    achados = pncp_busca.buscar_opcoes(
                        "municipios", filtros["municipio"], limite=1)
                    muns = [a["id"] for a in achados]
                resultado_vivo = pncp_busca.pesquisar(
                    q=filtros.get("q", ""),
                    ufs=[filtros["uf"]] if filtros.get("uf") else None,
                    modalidades=[filtros["modalidade"]]
                        if filtros.get("modalidade") else None,
                    municipios=muns or None, status="abertas")
                vivo_total = resultado_vivo["total"]
                salvos = {l[0] for l in
                          s.query(Licitacao.numero_controle_pncp)}
                for item in resultado_vivo["itens"]:
                    item["ja_salvo"] = item["numero_controle_pncp"] in salvos
                vivo = resultado_vivo["itens"]
            except Exception:  # noqa: BLE001 — sem PNCP, fica só o aviso
                pass
        def link(**mudar):
            """Monta a URL da tabela trocando só os parâmetros indicados —
            usada pelos menus de coluna (ordenar/filtrar sem perder o resto)."""
            params = {k: v for k, v in filtros.items() if v}
            params.update(mudar)
            return "/licitacoes?" + urlencode(
                {k: v for k, v in params.items() if v not in (None, "")})

        return templates.TemplateResponse(request, "licitacoes.html", {
            "linhas": linhas, "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // POR_PAGINA)), "filtros": filtros,
            "perfis": perfis, "ufs": ufs, "matches": matches,
            "modalidades": modalidades, "situacoes": situacoes,
            "vivo": vivo, "vivo_total": vivo_total, "link": link,
            "hoje": agora().strftime("%Y-%m-%d"),
            "em7": (agora() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "em30": (agora() + timedelta(days=30)).strftime("%Y-%m-%d"),
            # querystring só com os filtros (sem 'pagina'), para paginação/export
            "query": urlencode({k: v for k, v in filtros.items() if v}),
        })
    finally:
        s.close()


@app.get("/licitacoes/{lic_id}/detalhe", response_class=HTMLResponse)
async def licitacao_detalhe(request: Request, lic_id: int, perfil_id: int = 0):
    s = Sessao()
    try:
        lic = s.get(Licitacao, lic_id)
        if not lic:
            return HTMLResponse("Licitação não encontrada.", status_code=404)
        consulta = s.query(PerfilMatch).filter_by(licitacao_id=lic_id)
        if perfil_id:
            consulta = consulta.filter_by(perfil_id=perfil_id)
        matches = consulta.all()
        for m in matches:            # abrir o detalhe marca como lido
            m.lido = True
        s.commit()
        arquivos = s.query(ArquivoEdital).filter_by(licitacao_id=lic_id).all()
        return templates.TemplateResponse(request, "_licitacao_detalhe.html",
                                          {"lic": lic, "matches": matches,
                                           "arquivos": arquivos})
    finally:
        s.close()


@app.post("/licitacoes/{lic_id}/baixar", response_class=HTMLResponse)
async def licitacao_baixar_docs(request: Request, lic_id: int):
    """Busca e baixa agora os documentos publicados desta licitação."""
    s = Sessao()
    try:
        lic = s.get(Licitacao, lic_id)
        if not lic:
            return HTMLResponse("Licitação não encontrada.", status_code=404)
        baixar_arquivos(s, lic)
        arquivos = s.query(ArquivoEdital).filter_by(licitacao_id=lic_id).all()
        return templates.TemplateResponse(request, "_arquivos.html",
                                          {"lic": lic, "arquivos": arquivos})
    finally:
        s.close()


@app.get("/arquivos/{arquivo_id}")
async def arquivo_download(arquivo_id: int):
    """Entrega um documento já baixado (PDF do edital etc.)."""
    s = Sessao()
    try:
        arq = s.get(ArquivoEdital, arquivo_id)
        if not arq:
            return HTMLResponse("Arquivo não encontrado.", status_code=404)
        caminho = os.path.join(PASTA_DADOS, arq.caminho_local)
        if not os.path.exists(caminho):
            return HTMLResponse("Arquivo sumiu do disco.", status_code=404)
        return FileResponse(caminho, filename=os.path.basename(caminho))
    finally:
        s.close()


# ----------------------------------------------------------------------- atas
@app.get("/atas", response_class=HTMLResponse)
async def atas_lista(request: Request, q: str = "", adesao: str = "",
                     pagina: int = 1):
    pagina = max(1, pagina)
    s = Sessao()
    try:
        hoje = agora().strftime("%Y-%m-%d")
        consulta = (s.query(Ata).filter(Ata.cancelado.is_(False))
                    .filter(Ata.vigencia_fim >= hoje))
        if q:
            consulta = consulta.filter(Ata.objeto.ilike(f"%{q}%"))
        if adesao:
            consulta = consulta.filter(Ata.possibilidade_adesao.is_(True))
        total = consulta.count()
        linhas = (consulta.order_by(Ata.vigencia_fim)
                  .offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all())
        return templates.TemplateResponse(request, "atas.html", {
            "linhas": linhas, "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // POR_PAGINA)),
            "q": q, "adesao": adesao,
        })
    finally:
        s.close()


@app.post("/matches/{match_id}", response_class=HTMLResponse)
async def match_atualizar(match_id: int, status: str = Form(None),
                          favorito: str = Form(None), anotacao: str = Form(None)):
    s = Sessao()
    try:
        m = s.get(PerfilMatch, match_id)
        if not m:
            return HTMLResponse("Match não encontrado.", status_code=404)
        if status in ("novo", "analisando", "vou_participar", "descartado"):
            m.status = status
        if favorito is not None:
            m.favorito = favorito == "on"
        if anotacao is not None:
            m.anotacao = anotacao
        s.commit()
        return HTMLResponse('<span class="text-green-700 text-xs">✔ salvo</span>')
    finally:
        s.close()


@app.get("/licitacoes/exportar")
async def licitacoes_exportar(request: Request, formato: str = "csv"):
    s = Sessao()
    try:
        linhas = _consulta_licitacoes(s, _filtros_da_request(request)).all()
        if formato == "xlsx":
            return Response(
                gerar_xlsx(linhas),
                media_type="application/vnd.openxmlformats-officedocument"
                           ".spreadsheetml.sheet",
                headers={"Content-Disposition":
                         'attachment; filename="licitacoes.xlsx"'})
        return Response(gerar_csv(linhas), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":
                                 'attachment; filename="licitacoes.csv"'})
    finally:
        s.close()


# ------------------------------------------------- pesquisa ao vivo no PNCP
UFS_TODAS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG",
             "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR",
             "RS", "SC", "SE", "SP", "TO"]


def _perfil_pesquisa_manual(s):
    """Perfil-sistema que abriga o que você salva da pesquisa ao vivo."""
    p = s.query(PerfilBusca).filter_by(nome="⭐ Salvos da pesquisa").first()
    if not p:
        p = PerfilBusca(nome="⭐ Salvos da pesquisa", ativo=False,
                        notificar=False, ufs=[], modalidades=[],
                        palavras_incluir=["__nunca_casa_automaticamente__"])
        s.add(p)
        s.commit()
    return p


@app.get("/pesquisar", response_class=HTMLResponse)
async def pesquisar_pncp(request: Request, q: str = "", status: str = "abertas",
                         ordenacao: str = "recentes", pagina: int = 1,
                         frase_exata: str = "", cidade: str = "",
                         valor_min: str = "", valor_max: str = ""):
    qp = request.query_params
    f_ufs = qp.getlist("ufs")
    f_mods = [m for m in qp.getlist("modalidades") if m.isdigit()]
    f_esferas = [e for e in qp.getlist("esferas") if e in ("M", "E", "F", "D")]
    f_muns = [m for m in qp.getlist("municipios") if m.isdigit()]
    f_orgs = [o for o in qp.getlist("orgaos") if o.isdigit()]
    consultou = bool(q or f_ufs or f_mods or f_esferas or f_muns or f_orgs)
    resultado, erro, filtrados_pagina = {"total": 0, "itens": []}, None, 0
    if consultou:
        termo = f'"{q}"' if (q and frase_exata and '"' not in q) else q
        try:
            resultado = pncp_busca.pesquisar(
                q=termo, ufs=f_ufs, modalidades=f_mods, esferas=f_esferas,
                municipios=f_muns, orgaos=f_orgs,
                status=status, ordenacao=ordenacao, pagina=pagina)
        except Exception as e:  # noqa: BLE001
            erro = f"PNCP indisponível no momento: {e}"
        # refinamentos locais (a API não filtra cidade/valor): agem na página
        def _passa(it):
            if cidade and normalizar(cidade) not in \
                    normalizar(it.get("municipio_nome") or ""):
                return False
            v = it.get("valor_total_estimado")
            try:
                if valor_min and (v is None or v < float(valor_min)):
                    return False
                if valor_max and v is not None and v > float(valor_max):
                    return False
            except ValueError:
                pass
            return True
        if cidade or valor_min or valor_max:
            antes = len(resultado["itens"])
            resultado["itens"] = [i for i in resultado["itens"] if _passa(i)]
            filtrados_pagina = antes - len(resultado["itens"])
    s = Sessao()
    try:
        salvos = {l[0] for l in s.query(Licitacao.numero_controle_pncp)}
        modalidades = s.query(Modalidade).order_by(Modalidade.codigo).all()
    finally:
        s.close()
    for item in resultado["itens"]:
        item["ja_salvo"] = item["numero_controle_pncp"] in salvos
    return templates.TemplateResponse(request, "pesquisar.html", {
        "q": q, "status": status, "ordenacao": ordenacao, "pagina": pagina,
        "frase_exata": frase_exata, "cidade": cidade,
        "valor_min": valor_min, "valor_max": valor_max,
        "f_ufs": f_ufs, "f_mods": f_mods, "f_esferas": f_esferas,
        "f_muns": [(m, pncp_busca.nome_opcao("municipios", m)) for m in f_muns],
        "f_orgs": [(o, pncp_busca.nome_opcao("orgaos", o)) for o in f_orgs],
        "total": resultado["total"], "itens": resultado["itens"],
        "paginas": max(1, -(-resultado["total"] // 20)),
        "erro": erro, "ufs": UFS_TODAS, "modalidades": modalidades,
        "consultou": consultou, "filtrados_pagina": filtrados_pagina,
        "query_base": "&".join(
            [f"q={q}", f"status={status}", f"ordenacao={ordenacao}",
             f"frase_exata={frase_exata}", f"cidade={cidade}",
             f"valor_min={valor_min}", f"valor_max={valor_max}"] +
            [f"ufs={u}" for u in f_ufs] +
            [f"modalidades={m}" for m in f_mods] +
            [f"esferas={e}" for e in f_esferas] +
            [f"municipios={m}" for m in f_muns] +
            [f"orgaos={o}" for o in f_orgs]),
    })


@app.get("/api/pncp/opcoes", response_class=HTMLResponse)
async def pncp_opcoes(tipo: str = "municipios", q: str = ""):
    """Autocomplete de municípios e órgãos com os IDs do próprio portal."""
    if tipo not in ("municipios", "orgaos") or len(q) < 2:
        return HTMLResponse("")
    opcoes = pncp_busca.buscar_opcoes(tipo, q)
    if not opcoes:
        return HTMLResponse('<p class="px-3 py-1.5 text-xs text-slate-400">'
                            "Nada encontrado.</p>")
    linhas = []
    for o in opcoes:
        rotulo = o["nome"] + (f" ({o['cnpj']})" if o.get("cnpj") else "")
        linhas.append(
            f'<button type="button" class="block w-full text-left px-3 py-1.5 '
            f'text-xs hover:bg-blue-50" onclick="addFiltro(\'{tipo}\', '
            f'\'{o["id"]}\', this.textContent.trim())">{rotulo}</button>')
    return HTMLResponse("".join(linhas))


@app.post("/pesquisar/salvar", response_class=HTMLResponse)
async def pesquisar_salvar(request: Request):
    """Salva um resultado da pesquisa ao vivo no radar (entra no funil)."""
    form = await request.form()
    numero = form.get("numero_controle_pncp", "")
    if not numero:
        return HTMLResponse("item inválido", status_code=400)
    item = {c: (form.get(c) or None) for c in
            ("numero_controle_pncp", "objeto", "modalidade_nome", "orgao_nome",
             "orgao_cnpj", "municipio_nome", "uf", "data_abertura_proposta",
             "data_encerramento_proposta", "data_publicacao_pncp",
             "link_pncp", "situacao")}
    item["fonte"] = "pncp"
    item["objeto_norm"] = normalizar(item.get("objeto") or "")
    try:
        item["valor_total_estimado"] = float(form.get("valor_total_estimado"))
    except (TypeError, ValueError):
        item["valor_total_estimado"] = None
    m_cod = form.get("modalidade_codigo")
    item["modalidade_codigo"] = int(m_cod) if m_cod and m_cod.isdigit() else None
    ano = numero.split("/")[-1]
    item["ano_compra"] = int(ano) if ano.isdigit() else None
    s = Sessao()
    try:
        from .coleta import _upsert
        lic = _upsert(s, item)
        s.commit()
        perfil = _perfil_pesquisa_manual(s)
        existe = s.query(PerfilMatch).filter_by(
            perfil_id=perfil.id, licitacao_id=lic.id).first()
        if not existe:
            s.add(PerfilMatch(perfil_id=perfil.id, licitacao_id=lic.id,
                              termos="salvo manualmente"))
            s.commit()
        return HTMLResponse('<span class="text-green-700 text-xs '
                            'font-semibold">✔ no radar</span>')
    finally:
        s.close()


# ----------------------------------------------------------------------- logs
@app.get("/logs", response_class=HTMLResponse)
async def logs_coletas(request: Request):
    s = Sessao()
    try:
        registros = (s.query(ColetaLog)
                     .order_by(ColetaLog.inicio.desc()).limit(60).all())
        return templates.TemplateResponse(request, "logs.html",
                                          {"registros": registros})
    finally:
        s.close()


# --------------------------------------------------------------------- config
@app.get("/config", response_class=HTMLResponse)
async def config_form(request: Request, salvo: int = 0):
    return templates.TemplateResponse(request, "config.html", {
        "valores": envcfg.valores_atuais(), "salvo": salvo, "resultado_teste": None,
    })


@app.post("/config")
async def config_salvar(request: Request):
    form = await request.form()
    envcfg.salvar(dict(form))
    # Reagenda a coleta com o novo horário, sem reiniciar. O job de alertas
    # é de intervalo fixo: quem manda na hora é cada perfil.
    agendador.reschedule_job("coleta", trigger="cron", **_gatilho_coleta())
    return RedirectResponse("/config?salvo=1", status_code=303)


@app.post("/config/testar", response_class=HTMLResponse)
async def config_testar(request: Request, canal: str = Form("telegram")):
    """Botão 'Enviar mensagem de teste' (SPEC §7)."""
    texto = ("📡 Radar de Licitações — mensagem de teste.\n"
             "Se você recebeu isto, o canal está configurado corretamente. ✅")
    if canal == "email":
        ok = alerta_mod.enviar_email(texto)
    else:
        ok = alerta_mod.enviar_telegram(texto)
    cor = "text-green-700" if ok else "text-red-700"
    msg = ("✔ Teste enviado — confira se chegou." if ok else
           "✖ Falhou. Confira os dados e veja o terminal para detalhes.")
    return HTMLResponse(f'<span class="{cor} text-sm font-semibold">{msg}</span>')


# ------------------------------------------------------------------- execução
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
