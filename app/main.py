"""Radar de Licitações — servidor web (FastAPI) + agendador (APScheduler).

Subir com:  uvicorn app.main:app  (ou  python -m app.main)
"""
import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlencode

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, RedirectResponse,
                               Response)
from fastapi.templating import Jinja2Templates

from . import alerta as alerta_mod
from . import envcfg
from . import pncp_busca
from .coleta import coleta_em_andamento, coletar_em_background
from .config import PASTA_DADOS, config
from .db import (ArquivoEdital, Ata, ColetaLog, Licitacao, Modalidade,
                 Municipio, PerfilBusca, PerfilMatch, Sessao, criar_tabelas)
from .documentos import baixar_arquivos
from .exportar import gerar_csv, gerar_xlsx
from .matcher import licitacao_casa_perfil, normalizar
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
    # Coletas que ficaram "em andamento" (processo reiniciado no meio) são fechadas
    s = Sessao()
    try:
        s.query(ColetaLog).filter(ColetaLog.fim.is_(None)).update(
            {"fim": datetime.now(), "sucesso": False,
             "detalhe_erro": "coleta interrompida por reinício do aplicativo"})
        s.commit()
    finally:
        s.close()
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


# ------------------------------------------------------------------ dashboard
def _dias_ate(data_iso):
    try:
        alvo = datetime.strptime(data_iso[:10], "%Y-%m-%d")
        return (alvo - datetime.now()).days + 1
    except (ValueError, TypeError):
        return None


@app.get("/", response_class=HTMLResponse)
async def painel(request: Request):
    s = Sessao()
    try:
        def conta(status):
            return s.query(PerfilMatch).filter_by(status=status).count()

        hoje = datetime.now().strftime("%Y-%m-%d")
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
    hoje = datetime.now().strftime("%Y-%m-%d")
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
        hoje = datetime.now().strftime("%Y-%m-%d")
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
        "modo_busca": form.get("modo_busca", "ou"),
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


# ----------------------------------------------------------------- licitações
ORDENACOES_LISTA = {
    "encerramento_asc": (Licitacao.data_encerramento_proposta, False),
    "encerramento_desc": (Licitacao.data_encerramento_proposta, True),
    "publicacao_desc": (Licitacao.data_publicacao_pncp, True),
    "publicacao_asc": (Licitacao.data_publicacao_pncp, False),
    "valor_desc": (Licitacao.valor_total_estimado, True),
    "valor_asc": (Licitacao.valor_total_estimado, False),
    "uf_asc": (Licitacao.uf, False),
    "modalidade_asc": (Licitacao.modalidade_nome, False),
}
POR_PAGINA = 50


def _consulta_licitacoes(s, filtros):
    """Monta a consulta a partir dos filtros da tela (também usada na exportação)."""
    consulta = s.query(Licitacao)
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
    coluna, desc = ORDENACOES_LISTA.get(filtros.get("ordenar") or "",
                                        ORDENACOES_LISTA["encerramento_asc"])
    return consulta.order_by(coluna.desc() if desc else coluna.asc())


def _filtros_da_request(request):
    campos = ("perfil_id", "status", "uf", "municipio", "modalidade",
              "situacao", "data_ini", "data_fim", "q", "ordenar")
    return {c: request.query_params.get(c, "").strip() for c in campos}


@app.get("/licitacoes", response_class=HTMLResponse)
async def licitacoes_lista(request: Request, pagina: int = 1):
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
        return templates.TemplateResponse(request, "licitacoes.html", {
            "linhas": linhas, "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // POR_PAGINA)), "filtros": filtros,
            "perfis": perfis, "ufs": ufs, "matches": matches,
            "modalidades": modalidades, "situacoes": situacoes,
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
    s = Sessao()
    try:
        hoje = datetime.now().strftime("%Y-%m-%d")
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
async def pesquisar_pncp(request: Request, q: str = "", uf: str = "",
                         status: str = "abertas", pagina: int = 1):
    resultado, erro = {"total": 0, "itens": []}, None
    if q or uf:
        try:
            resultado = pncp_busca.pesquisar(q=q, uf=uf, status=status,
                                             pagina=pagina)
        except Exception as e:  # noqa: BLE001
            erro = f"PNCP indisponível no momento: {e}"
    s = Sessao()
    try:
        salvos = {l[0] for l in s.query(Licitacao.numero_controle_pncp)}
    finally:
        s.close()
    for item in resultado["itens"]:
        item["ja_salvo"] = item["numero_controle_pncp"] in salvos
    return templates.TemplateResponse(request, "pesquisar.html", {
        "q": q, "uf": uf, "status": status, "pagina": pagina,
        "total": resultado["total"], "itens": resultado["itens"],
        "paginas": max(1, -(-resultado["total"] // 20)),
        "erro": erro, "ufs": UFS_TODAS,
    })


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
    # Reagenda os jobs com os novos horários, sem reiniciar
    h, m = config.HORA_COLETA
    agendador.reschedule_job("coleta", trigger="cron", hour=h, minute=m)
    h, m = config.HORA_ALERTA
    agendador.reschedule_job("alerta", trigger="cron", hour=h, minute=m)
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
