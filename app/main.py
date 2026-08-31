"""Licerta — servidor web (FastAPI) + agendador (APScheduler).

Subir com:  uvicorn app.main:app  (ou  python -m app.main)
"""
import json
import logging
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from html import escape
from urllib.parse import quote, urlencode

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, RedirectResponse,
                               Response)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .notificacoes import alerta as alerta_mod
from .notificacoes import push as push_mod
from . import usuarios as usuarios_mod
from . import envcfg
from . import vigia as vigia_mod
from .ingestao import pncp_busca
from . import sincronizar
from .radar.coleta import (MSG_INTERROMPIDA, coleta_em_andamento,
                           coletar_em_background)
from .config import PASTA_DADOS, VERSAO, agora, config, hoje
from .db import (ArquivoEdital, Ata, ColetaLog, DocumentoEmpresa, EditalFicha,
                 EmpresaDados, Licitacao, LicitacaoAlteracao, Minuta,
                 Modalidade, Municipio, PerfilBusca, PerfilMatch,
                 PushAssinatura, Sessao, Usuario, VigiaProblema,
                 criar_tabelas)
from .documentos import validades as validades_mod
from .editais.analise import SemChaveIA, analisar_edital
from .editais.arquivos import baixar_arquivos
from .exportar import gerar_csv, gerar_xlsx
from .radar.matcher import (SITUACOES_CONHECIDAS, SITUACOES_DISPUTAVEIS,
                      licitacao_casa_perfil, normalizar)
from .seed import semear

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("radar")

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates"))


def _filtro_quando(iso):
    """Data ISO no jeito que uma pessoa lê: 'hoje 08:00', 'amanhã', '05/09'."""
    if not iso:
        return "—"
    try:
        dia, hora = iso[:10], iso[11:16]
        alvo = datetime.strptime(dia, "%Y-%m-%d").date()
        hoje = agora().date()
        dif = (alvo - hoje).days
        if dif == 0:
            rotulo = "hoje"
        elif dif == 1:
            rotulo = "amanhã"
        else:
            rotulo = alvo.strftime("%d/%m") + ("" if alvo.year == hoje.year
                                               else alvo.strftime("/%Y"))
        return f"{rotulo} {hora}".strip() if hora else rotulo
    except (ValueError, TypeError):
        return iso


def _filtro_dinheiro(valor):
    if not valor:
        return "—"          # zero e nulo são igualmente "não informado"
    if valor >= 1_000_000:
        return f"R$ {valor / 1_000_000:.1f} mi".replace(".", ",")
    if valor >= 1_000:
        return f"R$ {valor / 1_000:.0f} mil"
    return f"R$ {valor:.0f}"


templates.env.filters["quando"] = _filtro_quando
templates.env.filters["dinheiro"] = _filtro_dinheiro

agendador = BackgroundScheduler(timezone=config.TZ)


def _job_coleta():
    """Job diário de coleta. Roda em thread própria; nunca derruba o agendador."""
    try:
        from .radar.coleta import coletar
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


def _job_validades():
    """Vigia diário do dossiê: certidão vencendo vira aviso aos admins."""
    try:
        validades_mod.avisar_vencimentos()
    except Exception:  # noqa: BLE001
        log.exception("Erro no job de validades")


def _job_vigia():
    """O radar vigia a si mesmo: detecta falha silenciosa e avisa os admins."""
    try:
        vigia_mod.vigiar()
    except Exception:  # noqa: BLE001
        log.exception("Erro no job do vigia")


@asynccontextmanager
async def vida(app_):
    criar_tabelas()
    semear()
    # Coletas que ficaram "em andamento" (processo reiniciado no meio) são fechadas
    s = Sessao()
    try:
        s.query(ColetaLog).filter(ColetaLog.fim.is_(None)).update(
            {"fim": agora(), "sucesso": False,
             "detalhe_erro": MSG_INTERROMPIDA})
        s.commit()
    finally:
        s.close()
    # O app se cura de um volume cheio ao subir: sem espaço em disco, até
    # gravar o .env falha (foi um 500 real em produção em 31/08/2026).
    s = Sessao()
    try:
        from .editais.arquivos import podar_cache
        podar_cache(s)
    except Exception:  # noqa: BLE001
        log.exception("Poda do cache no startup falhou")
    finally:
        s.close()
    agendador.add_job(_job_coleta, "cron", id="coleta", replace_existing=True,
                      **_gatilho_coleta())
    agendador.add_job(_job_alerta, "interval", minutes=10, id="alerta",
                      replace_existing=True)
    # De meia em meia hora: rápido o bastante para pegar coleta morta no
    # mesmo dia, espaçado o bastante para o primeiro ciclo já nascer fora
    # da janela de carência do boot.
    agendador.add_job(_job_vigia, "interval", minutes=30, id="vigia",
                      replace_existing=True)
    h_alerta, m_alerta = config.HORA_ALERTA
    agendador.add_job(_job_validades, "cron", hour=h_alerta, minute=m_alerta,
                      id="validades", replace_existing=True)
    if not agendador.running:
        agendador.start()
    log.info("Agendador ativo: coleta às %sh; alertas conferidos a cada "
             "10 min, cada um na sua frequência (%s)",
             _gatilho_coleta()["hour"], config.TZ)
    yield
    if agendador.running:
        agendador.shutdown(wait=False)


app = FastAPI(title="Licerta", lifespan=vida)
app.mount("/static", StaticFiles(
    directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


# ---------------------------------------------------------------- autenticação
CAMINHO_SEGREDO = os.path.join(PASTA_DADOS, ".segredo_sessao")


# Reserva para quando a pasta de dados não aceitar escrita: sem isto, o
# login inteiro caía com erro 500 e ninguém entrava no app — nem o dono.
_SEGREDO_MEMORIA = secrets.token_bytes(32)


def _segredo_sessao():
    """Chave aleatória do cookie, guardada fora do código e fora do git.

    Antes a chave era a literal b"radar-licitacoes", pública no repositório:
    o cookie virava um HMAC de chave conhecida sobre a senha, então quem o
    obtivesse quebrava a senha por força bruta OFFLINE — e a mesma senha
    abre a tela que mostra o token do Telegram e a senha do e-mail.

    Se não der para gravar o arquivo, usa uma chave de memória: as sessões
    passam a valer só enquanto o processo estiver de pé, mas entrar no app
    continua funcionando. Nunca vale a pena trancar o dono do lado de fora.
    """
    try:
        with open(CAMINHO_SEGREDO, "rb") as f:
            segredo = f.read()
        if len(segredo) >= 32:
            return segredo
    except OSError:
        pass
    try:
        segredo = secrets.token_bytes(32)
        with open(CAMINHO_SEGREDO, "wb") as f:
            f.write(segredo)
        return segredo
    except OSError as e:
        log.warning("Sem escrita em %s (%s); a sessão vale só até reiniciar",
                    CAMINHO_SEGREDO, e)
        return _SEGREDO_MEMORIA


def usuario_da_requisicao(request: Request):
    """O usuário logado desta requisição (ou None)."""
    return usuarios_mod.usuario_do_token(
        request.cookies.get("sessao", ""), _segredo_sessao())


def _sem_usuarios():
    s = Sessao()
    try:
        return s.query(Usuario).count() == 0
    finally:
        s.close()


ROTAS_LIVRES = ("/login", "/registrar", "/manifest.json", "/sw.js",
                "/api/saude")


@app.get("/api/saude")
async def saude():
    """Sinal de vida público e sem dado sensível: versão e hora do processo.

    Serve ao healthcheck da hospedagem e ao vigia externo (rotina do
    Actions) — e a nós, para saber qual versão está de pé após um deploy.
    `problemas` é só a CONTAGEM do vigia interno: o detalhe fica atrás do
    login, no painel e em /logs.
    """
    s = Sessao()
    try:
        problemas = s.query(VigiaProblema).count()
    finally:
        s.close()
    return {"app": "licerta", "versao": VERSAO,
            "hora": agora().isoformat(timespec="seconds"),
            "problemas": problemas}


@app.middleware("http")
async def exigir_login(request: Request, call_next):
    caminho = request.url.path
    livre = caminho in ROTAS_LIVRES or caminho.startswith("/static")
    if not livre:
        usuario = usuario_da_requisicao(request)
        if not usuario:
            return RedirectResponse("/login", status_code=303)
        request.state.usuario = usuario
    return await call_next(request)


def eu(request: Request):
    """O usuário logado, já carregado pelo middleware."""
    return request.state.usuario


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if _sem_usuarios():
        return RedirectResponse("/registrar", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"erro": None})


@app.get("/registrar", response_class=HTMLResponse)
async def registrar_form(request: Request):
    """Primeiro acesso de uma instalação nova: cria a conta do administrador.

    Só existe enquanto não há nenhum usuário — depois disso, contas novas
    são criadas pelo administrador na tela Usuários. Assim uma URL pública
    não vira balcão de cadastro aberto.
    """
    if not _sem_usuarios():
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "registrar.html", {"erro": None})


@app.post("/registrar")
async def registrar(request: Request, nome: str = Form(""),
                    email: str = Form(""), senha: str = Form("")):
    if not _sem_usuarios():
        return RedirectResponse("/login", status_code=303)
    nome, email = nome.strip(), email.strip().lower()
    if not (nome and "@" in email and len(senha) >= 6):
        return templates.TemplateResponse(
            request, "registrar.html",
            {"erro": "Preencha nome, um e-mail válido e uma senha de pelo "
                     "menos 6 caracteres."})
    s = Sessao()
    try:
        admin = Usuario(nome=nome, email=email, papel="admin",
                        senha_hash=usuarios_mod.gerar_hash(senha),
                        email_alertas=email)
        s.add(admin)
        s.commit()
        resposta = RedirectResponse("/conta?bemvindo=1", status_code=303)
        _pendurar_sessao(resposta, admin)
        return resposta
    finally:
        s.close()


def _pendurar_sessao(resposta, usuario):
    resposta.set_cookie(
        "sessao", usuarios_mod.criar_token(usuario, _segredo_sessao()),
        httponly=True, samesite="lax", secure=config.COOKIE_SEGURO,
        max_age=usuarios_mod.VALIDADE_SESSAO)


# Freio de força bruta. O app está numa URL pública e a senha é a defesa
# inteira: sem isso, uma wordlist roda à vontade contra /login.
TENTATIVAS_ANTES_DE_ESPERAR = 5
ESPERA_MAXIMA = 15 * 60
_falhas_login = {}


def _tempo_de_castigo(ip):
    """Segundos que ainda faltam para este IP poder tentar de novo."""
    falhas, ultima = _falhas_login.get(ip, (0, 0))
    if falhas < TENTATIVAS_ANTES_DE_ESPERAR:
        return 0
    espera = min(ESPERA_MAXIMA, 2 ** (falhas - TENTATIVAS_ANTES_DE_ESPERAR) * 5)
    return max(0, int(ultima + espera - time.monotonic()))


@app.post("/login")
def login(request: Request, email: str = Form(""), senha: str = Form("")):
    ip = request.client.host if request.client else "?"
    faltam = _tempo_de_castigo(ip)
    if faltam:
        return templates.TemplateResponse(
            request, "login.html",
            {"erro": f"Muitas tentativas. Tente de novo em {faltam}s."},
            status_code=429)
    usuario = usuarios_mod.autenticar(email, senha)
    if usuario:
        _falhas_login.pop(ip, None)
        resposta = RedirectResponse("/", status_code=303)
        _pendurar_sessao(resposta, usuario)
        return resposta
    falhas, _ = _falhas_login.get(ip, (0, 0))
    _falhas_login[ip] = (falhas + 1, time.monotonic())
    log.warning("Login recusado (origem %s, %sª falha)", ip, falhas + 1)
    return templates.TemplateResponse(
        request, "login.html", {"erro": "E-mail ou senha incorretos."})


@app.get("/logout")
async def logout():
    # Sai só DESTE aparelho. Para derrubar todas as sessões da conta —
    # cookie roubado, por exemplo — troque a senha: o token assina a senha
    # e morre junto com ela.
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
        meus = (PerfilBusca.usuario_id == eu(request).id)

        def conta(status):
            return (s.query(PerfilMatch).join(PerfilBusca)
                    .filter(PerfilMatch.status == status, meus).count())

        hoje = agora().strftime("%Y-%m-%d")
        ativos = (s.query(PerfilMatch).join(Licitacao).join(PerfilBusca)
                  .filter(meus, PerfilMatch.status != "descartado",
                          Licitacao.data_encerramento_proposta >= hoje)
                  .order_by(Licitacao.data_encerramento_proposta))
        urgentes = [m for m in ativos
                    if (_dias_ate(m.licitacao.data_encerramento_proposta) or 99) <= 7]
        proximos = [{"lic": m.licitacao, "status": m.status,
                     "dias": _dias_ate(m.licitacao.data_encerramento_proposta)}
                    for m in ativos.limit(8)]
        kpis = {"novas": conta("novo"), "analisando": conta("analisando"),
                "participar": conta("vou_participar"), "urgentes": len(urgentes)}
        fecham_hoje = sum(1 for m in urgentes
                          if (m.licitacao.data_encerramento_proposta
                              or "")[:10] == hoje)
        # A última coleta CONCLUÍDA, com ou sem tropeços: uma varredura que
        # trouxe 900 editais e falhou numa combinação continua sendo coleta.
        ultima = (s.query(ColetaLog).filter(ColetaLog.fim.isnot(None))
                  .order_by(ColetaLog.fim.desc()).first())
        ultimas = (s.query(Licitacao)
                   .order_by(Licitacao.coletado_em.desc()).limit(8).all())
        # Primeiros passos: a tela inicial de quem acabou de chegar precisa
        # dizer O QUE FAZER, não mostrar zeros. Some sozinha quando os três
        # passos estão completos.
        usuario = s.get(Usuario, eu(request).id)
        passos = {
            "perfil": s.query(PerfilBusca).filter(
                meus, PerfilBusca.nome != sincronizar.PERFIL_SISTEMA
            ).count() > 0,
            "avisos": bool(
                (usuario.receber_telegram and usuario.telegram_chat_id)
                or (usuario.receber_email and usuario.email_alertas)
                or (usuario.receber_push and usuario.assinaturas_push)),
            "coleta": bool(ultimas),       # o radar já tem dados?
        }
        # Certidão vencendo interessa a TODOS (o dossiê é da empresa).
        docs_alerta = []
        consulta_docs = (s.query(DocumentoEmpresa).filter_by(arquivado=False)
                         .filter(DocumentoEmpresa.validade.isnot(None)))
        for d in consulta_docs:
            situ, dias = validades_mod.situacao_documento(d)
            if situ in ("vencido", "vencendo"):
                docs_alerta.append({"doc": d, "situacao": situ, "dias": dias})
        docs_alerta.sort(key=lambda x: x["dias"])
        # Problemas do vigia: assunto de quem opera a instalação. Para os
        # demais usuários o painel segue limpo — eles não têm o que fazer.
        problemas = (s.query(VigiaProblema).order_by(VigiaProblema.desde).all()
                     if eu(request).papel == "admin" else [])
        return templates.TemplateResponse(request, "painel.html", {
            "kpis": kpis, "proximos": proximos, "ultima_coleta": ultima,
            "ultimas": ultimas, "coletando": coleta_em_andamento(),
            "hora_coleta": config.HORA_COLETA,
            "fecham_hoje": fecham_hoje, "problemas": problemas,
            "docs_alerta": docs_alerta,
            "passos": passos, "tudo_pronto": all(passos.values()),
        })
    finally:
        s.close()


# ---------------------------------------------------------- funil (kanban)
COLUNAS_FUNIL = [("novo", "🟡 Novas"), ("analisando", "🔵 Em análise"),
                 ("vou_participar", "🟢 Vou participar"),
                 ("descartado", "⚪ Descartadas")]


def _contexto_funil(s, usuario):
    hoje = agora().strftime("%Y-%m-%d")
    colunas = []
    for status, rotulo in COLUNAS_FUNIL:
        consulta = (s.query(PerfilMatch).join(Licitacao).join(PerfilBusca)
                    .filter(PerfilMatch.status == status,
                            PerfilBusca.usuario_id == usuario.id)
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
                                          _contexto_funil(s, eu(request)))
    finally:
        s.close()


@app.post("/funil/mover/{match_id}/{status}", response_class=HTMLResponse)
async def funil_mover(request: Request, match_id: int, status: str):
    s = Sessao()
    try:
        m = s.get(PerfilMatch, match_id)
        meu = m and m.perfil and m.perfil.usuario_id == eu(request).id
        if meu and status in ("novo", "analisando", "vou_participar",
                              "descartado"):
            m.status = status
            m.lido = True
            s.commit()
        return templates.TemplateResponse(request, "_funil_board.html",
                                          _contexto_funil(s, eu(request)))
    finally:
        s.close()


# --------------------------------------------------------------------- agenda
@app.get("/agenda", response_class=HTMLResponse)
async def agenda(request: Request):
    s = Sessao()
    try:
        hoje = agora().strftime("%Y-%m-%d")
        matches = (s.query(PerfilMatch).join(Licitacao).join(PerfilBusca)
                   .filter(PerfilMatch.status != "descartado",
                           PerfilBusca.usuario_id == eu(request).id,
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
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                rotulo = f"{dt.strftime('%d/%m/%Y')} ({semana[dt.weekday()]})"
            except (ValueError, TypeError):
                # O Mural do TCE-PI já gravou datas impossíveis ("2026-13-45"),
                # que passam no filtro por serem comparadas como texto. Uma
                # linha torta não pode derrubar a agenda inteira.
                rotulo = d or "data inválida"
            agenda_dias.append({
                "data": d,
                "rotulo": rotulo,
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
        "modalidades": [int(m) for m in form.getlist("modalidades")
                        if str(m).strip().isdigit()],
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
        perfis = (s.query(PerfilBusca)
                  .filter_by(usuario_id=eu(request).id)
                  .order_by(PerfilBusca.nome).all())
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
        if not perfil or perfil.usuario_id != eu(request).id:
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
        if perfil and perfil.usuario_id != eu(request).id:
            return RedirectResponse("/perfis", status_code=303)
        if perfil:
            for campo, valor in dados.items():
                setattr(perfil, campo, valor)
        else:
            s.add(PerfilBusca(**dados, usuario_id=eu(request).id))
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
async def perfil_toggle(request: Request, perfil_id: int):
    s = Sessao()
    try:
        perfil = s.get(PerfilBusca, perfil_id)
        if perfil and perfil.usuario_id == eu(request).id:
            perfil.ativo = not perfil.ativo
            s.commit()
        return RedirectResponse("/perfis", status_code=303)
    finally:
        s.close()


@app.post("/perfis/{perfil_id}/duplicar")
async def perfil_duplicar(request: Request, perfil_id: int):
    s = Sessao()
    try:
        original = s.get(PerfilBusca, perfil_id)
        if original and original.usuario_id == eu(request).id:
            s.add(PerfilBusca(
                nome=f"{original.nome} (cópia)", ativo=False,
                usuario_id=original.usuario_id,
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


@app.get("/api/perfis/exportar")
async def perfis_exportar():
    """Configuração dos perfis em JSON, para o robô do e-mail e o PC puxarem.

    É o que mantém os três bancos (Railway, Actions, PC) com os MESMOS
    critérios: este app é a fonte da verdade e os outros sincronizam daqui.
    Protegida pelo login como tudo mais.
    """
    s = Sessao()
    try:
        return sincronizar.exportar_perfis(s)
    finally:
        s.close()


@app.post("/perfis/{perfil_id}/enviar")
def perfil_enviar_agora(perfil_id: int):
    """Botão 'Enviar agora': dispara este alerta fora da agenda."""
    enviados = alerta_mod.enviar_alertas_devidos(perfil_id=perfil_id)
    return RedirectResponse(f"/perfis?enviado={'sim' if enviados else 'vazio'}",
                            status_code=303)


@app.post("/perfis/{perfil_id}/excluir")
async def perfil_excluir(request: Request, perfil_id: int):
    s = Sessao()
    try:
        perfil = s.get(PerfilBusca, perfil_id)
        if perfil and perfil.usuario_id == eu(request).id:
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
def licitacoes_lista(request: Request, pagina: int = 1):
    # Teto além do máximo: o offset vai para o SQLite, que só aceita
    # 64 bits — sem teto, ?pagina=99999999999999999999 vira erro 500.
    pagina = max(1, min(pagina, 1_000_000))
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
        perfis = (s.query(PerfilBusca)
                  .filter_by(usuario_id=eu(request).id)
                  .order_by(PerfilBusca.nome).all())
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
def licitacao_detalhe(request: Request, lic_id: int, perfil_id: int = 0):
    s = Sessao()
    try:
        lic = s.get(Licitacao, lic_id)
        if not lic:
            return HTMLResponse("Licitação não encontrada.", status_code=404)
        consulta = (s.query(PerfilMatch).join(PerfilBusca)
                    .filter(PerfilMatch.licitacao_id == lic_id,
                            PerfilBusca.usuario_id == eu(request).id))
        if perfil_id:
            consulta = consulta.filter_by(perfil_id=perfil_id)
        matches = consulta.all()
        for m in matches:            # abrir o detalhe marca como lido
            m.lido = True
        s.commit()
        arquivos = s.query(ArquivoEdital).filter_by(licitacao_id=lic_id).all()
        ficha = s.query(EditalFicha).filter_by(licitacao_id=lic_id).first()
        from .radar.alteracoes import CAMPOS_VIGIADOS
        alteracoes = (s.query(LicitacaoAlteracao)
                      .filter_by(licitacao_id=lic_id)
                      .order_by(LicitacaoAlteracao.detectada_em.desc())
                      .limit(20).all())
        dados = _dados_ficha(ficha)
        minutas = (s.query(Minuta).filter_by(licitacao_id=lic_id)
                   .order_by(Minuta.criada_em.desc()).all())
        return templates.TemplateResponse(request, "_licitacao_detalhe.html",
                                          {"lic": lic, "matches": matches,
                                           "arquivos": arquivos,
                                           "ficha": ficha, "dados": dados,
                                           "alteracoes": alteracoes,
                                           "rotulos_alteracao": CAMPOS_VIGIADOS,
                                           "minutas": minutas,
                                           "sou_admin": _sou_admin(request),
                                           **_contexto_checklist(s, dados, lic)})
    finally:
        s.close()


def _dados_ficha(ficha):
    """O JSON da ficha como dict para o template — ou None, sem nunca quebrar."""
    if not (ficha and ficha.ficha_json):
        return None
    try:
        return json.loads(ficha.ficha_json)
    except ValueError:
        return None


def _contexto_checklist(s, dados, lic):
    """Extras da ficha: prazos em dias úteis (sempre que houver data de
    sessão) e o checklist exigência × dossiê (só quando há ficha E há
    documentos — dossiê vazio viraria uma coluna de 'falta' sem informação).
    """
    contexto = {"checklist": [], "checklist_sessao": None,
                "tem_dossie": False, "prazos": None}
    if not dados:
        return contexto
    from .acompanhamento.prazos import prazos_da_sessao
    from .documentos import checklist as checklist_mod
    sessao_data = checklist_mod.data_da_sessao(dados, lic)
    contexto["checklist_sessao"] = sessao_data
    contexto["prazos"] = prazos_da_sessao(sessao_data, hoje())
    docs = (s.query(DocumentoEmpresa).filter_by(arquivado=False).all())
    if not docs:
        return contexto
    itens, _ = checklist_mod.avaliar(dados, lic, docs)
    contexto.update({"checklist": itens, "tem_dossie": True})
    return contexto


@app.post("/licitacoes/{lic_id}/analisar", response_class=HTMLResponse)
def licitacao_analisar(request: Request, lic_id: int, forcar: int = Form(0)):
    """Gera (ou regera) a ficha do edital por IA e devolve o bloco pronto.

    Roda na hora, dentro do clique: a chamada de IA leva de 20 a 60
    segundos e o htmx segura o botão com o indicador. Ficha é ativo global
    (1× por edital) — quem clicar depois recebe a mesma, sem custo novo.
    """
    s = Sessao()
    try:
        lic = s.get(Licitacao, lic_id)
        if not lic:
            return HTMLResponse("Licitação não encontrada.", status_code=404)
        try:
            ficha = analisar_edital(s, lic, forcar=bool(forcar))
        except SemChaveIA as e:
            aviso = escape(str(e))
            extra = (' <a href="/config" class="underline">Abrir '
                     'configurações</a>' if _sou_admin(request) else "")
            return HTMLResponse(
                f'<div id="ficha{lic_id}" class="border border-indigo-200 '
                f'rounded-xl bg-indigo-50/40 p-4 text-xs text-slate-600">'
                f'🧠 {aviso}{extra}</div>')
        dados = _dados_ficha(ficha)
        return templates.TemplateResponse(request, "_ficha_edital.html", {
            "lic": lic, "ficha": ficha, "dados": dados,
            "sou_admin": _sou_admin(request),
            **_contexto_checklist(s, dados, lic)})
    finally:
        s.close()


@app.post("/licitacoes/{lic_id}/baixar", response_class=HTMLResponse)
def licitacao_baixar_docs(request: Request, lic_id: int):
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
    # Teto além do máximo: o offset vai para o SQLite, que só aceita
    # 64 bits — sem teto, ?pagina=99999999999999999999 vira erro 500.
    pagina = max(1, min(pagina, 1_000_000))
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
            "query_base": urlencode([("q", q), ("adesao", adesao)]),
        })
    finally:
        s.close()


@app.post("/matches/{match_id}", response_class=HTMLResponse)
async def match_atualizar(request: Request, match_id: int,
                          status: str = Form(None), favorito: str = Form(None),
                          anotacao: str = Form(None)):
    s = Sessao()
    try:
        m = s.get(PerfilMatch, match_id)
        if m and (not m.perfil or m.perfil.usuario_id != eu(request).id):
            m = None
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
def licitacoes_exportar(request: Request, formato: str = "csv"):
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


def _perfil_pesquisa_manual(s, usuario):
    """Perfil-sistema que abriga o que você salva da pesquisa ao vivo."""
    p = (s.query(PerfilBusca)
         .filter_by(nome="⭐ Salvos da pesquisa", usuario_id=usuario.id).first())
    if not p:
        p = PerfilBusca(nome="⭐ Salvos da pesquisa", ativo=False,
                        usuario_id=usuario.id,
                        notificar=False, ufs=[], modalidades=[],
                        palavras_incluir=["__nunca_casa_automaticamente__"])
        s.add(p)
        s.commit()
    return p


@app.get("/pesquisar", response_class=HTMLResponse)
def pesquisar_pncp(request: Request, q: str = "", status: str = "abertas",
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
        # urlencode, não f-string: uma busca por "reforma & ampliação" fazia
        # o '&' virar separador de parâmetro e a página 2 vinha com a consulta
        # truncada, mostrando resultados diferentes dos da página 1.
        "query_base": urlencode(
            [("q", q), ("status", status), ("ordenacao", ordenacao),
             ("frase_exata", frase_exata), ("cidade", cidade),
             ("valor_min", valor_min), ("valor_max", valor_max)] +
            [("ufs", u) for u in f_ufs] +
            [("modalidades", m) for m in f_mods] +
            [("esferas", e) for e in f_esferas] +
            [("municipios", m) for m in f_muns] +
            [("orgaos", o) for o in f_orgs]),
        "query_perfil": urlencode(
            [("q", q)] + [("ufs", u) for u in f_ufs]
            + [("modalidades", m) for m in f_mods]),
    })


@app.get("/api/pncp/opcoes", response_class=HTMLResponse)
def pncp_opcoes(tipo: str = "municipios", q: str = ""):
    """Autocomplete de municípios e órgãos com os IDs do próprio portal."""
    if tipo not in ("municipios", "orgaos") or len(q) < 2:
        return HTMLResponse("")
    opcoes = pncp_busca.buscar_opcoes(tipo, q)
    if not opcoes:
        return HTMLResponse('<p class="px-3 py-1.5 text-xs text-slate-400">'
                            "Nada encontrado.</p>")
    # Este HTML é montado à mão (não passa pelo Jinja), então o escape tem de
    # ser explícito: o nome do órgão vem cru da API do PNCP e um '<' ali
    # viraria markup executado no seu navegador já autenticado. Os dados vão
    # em data-*, nunca dentro de um onclick — nome com apóstrofo quebrava o
    # handler e o clique não fazia nada.
    linhas = []
    for o in opcoes:
        rotulo = o["nome"] + (f" ({o['cnpj']})" if o.get("cnpj") else "")
        linhas.append(
            f'<button type="button" class="block w-full text-left px-3 py-1.5 '
            f'text-xs hover:bg-blue-50" data-tipo="{escape(tipo)}" '
            f'data-id="{escape(str(o["id"]))}" '
            f'data-rotulo="{escape(rotulo)}">{escape(rotulo)}</button>')
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
        from .radar.coleta import _upsert
        lic = _upsert(s, item)
        s.commit()
        perfil = _perfil_pesquisa_manual(s, eu(request))
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
# ------------------------------------------------------------ peças (minutas)
@app.post("/licitacoes/{lic_id}/minuta", response_class=HTMLResponse)
def licitacao_minuta(request: Request, lic_id: int):
    """Gera a minuta de impugnação (camada 3, sob demanda) e abre a página."""
    from .pecas import minutas as minutas_mod
    s = Sessao()
    try:
        lic = s.get(Licitacao, lic_id)
        if not lic:
            return HTMLResponse("Licitação não encontrada.", status_code=404)
        ficha = s.query(EditalFicha).filter_by(licitacao_id=lic_id).first()
        try:
            minuta = minutas_mod.gerar_impugnacao(
                s, lic, _dados_ficha(ficha), usuario=eu(request))
        except (minutas_mod.MinutaIndevida, SemChaveIA) as e:
            corpo = escape(str(e))
            extra = (' <a href="/config" class="underline">Configurações</a>'
                     if isinstance(e, SemChaveIA) and _sou_admin(request)
                     else "")
            return HTMLResponse(
                f'<div class="text-xs bg-amber-50 border border-amber-300 '
                f'text-amber-900 rounded-lg px-3 py-2">📜 {corpo}{extra}</div>')
        # htmx segue para a página da minuta pronta
        resposta = HTMLResponse("")
        resposta.headers["HX-Redirect"] = f"/minutas/{minuta.id}"
        return resposta
    finally:
        s.close()


@app.get("/minutas/{minuta_id}", response_class=HTMLResponse)
def minuta_ver(request: Request, minuta_id: int):
    s = Sessao()
    try:
        minuta = s.get(Minuta, minuta_id)
        if not minuta:
            return HTMLResponse("Minuta não encontrada.", status_code=404)
        return templates.TemplateResponse(request, "minuta.html", {
            "minuta": minuta, "lic": minuta.licitacao,
            "sou_admin": _sou_admin(request)})
    finally:
        s.close()


@app.get("/minutas/{minuta_id}/baixar")
def minuta_baixar(request: Request, minuta_id: int):
    s = Sessao()
    try:
        minuta = s.get(Minuta, minuta_id)
        if not minuta:
            return HTMLResponse("Minuta não encontrada.", status_code=404)
        nome = f"minuta-{minuta.tipo}-{minuta.licitacao_id}.md"
        return Response(minuta.texto, media_type="text/markdown",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{nome}"'})
    finally:
        s.close()


@app.post("/config/empresa")
async def config_empresa(request: Request):
    """Identidade da empresa (linha única no banco) — entra nas minutas."""
    if not _sou_admin(request):
        return RedirectResponse("/", status_code=303)
    from .pecas.minutas import dados_empresa
    form = await request.form()
    s = Sessao()
    try:
        dados = dados_empresa(s)
        dados.razao_social = (form.get("razao_social") or "").strip()[:200]
        dados.cnpj = (form.get("cnpj") or "").strip()[:20]
        dados.endereco = (form.get("endereco") or "").strip()[:300]
        dados.representante_nome = (form.get("representante_nome")
                                    or "").strip()[:120]
        dados.representante_cargo = (form.get("representante_cargo")
                                     or "").strip()[:80]
        dados.atualizado_em = agora()
        s.commit()
        return RedirectResponse("/config?salvo=1", status_code=303)
    finally:
        s.close()


# ------------------------------------------------------ documentos da empresa
PASTA_DOCUMENTOS = os.path.join(PASTA_DADOS, "documentos")


def _contexto_documentos(s, aviso=None):
    docs = (s.query(DocumentoEmpresa)
            .order_by(DocumentoEmpresa.arquivado,
                      DocumentoEmpresa.validade.is_(None),
                      DocumentoEmpresa.validade).all())
    hoje_ = hoje()
    itens = []
    for d in docs:
        situacao, dias = validades_mod.situacao_documento(d, hoje_)
        itens.append({"doc": d, "situacao": situacao, "dias": dias})
    return {"itens": itens, "tipos": validades_mod.TIPOS, "aviso": aviso}


@app.get("/documentos", response_class=HTMLResponse)
async def documentos(request: Request, aviso: str = ""):
    s = Sessao()
    try:
        return templates.TemplateResponse(request, "documentos.html",
                                          _contexto_documentos(s, aviso))
    finally:
        s.close()


@app.post("/documentos")
async def documentos_upload(request: Request,
                            arquivo: UploadFile = File(None),
                            nome: str = Form(""), tipo: str = Form("Outro"),
                            validade: str = Form("")):
    """Sobe um documento do dossiê. Validade em branco + PDF legível =
    o app sugere a data lida do próprio arquivo (regex, nunca IA) — e diz
    que foi sugestão, para o usuário conferir."""
    s = Sessao()
    aviso = ""
    try:
        doc = DocumentoEmpresa(
            nome=(nome or "").strip()
                 or os.path.splitext(arquivo.filename or "Documento")[0][:80],
            tipo=(tipo or "Outro").strip()[:60],
            validade=_data_ou_nada(validade),
            enviado_por=eu(request).id)
        s.add(doc)
        s.flush()
        if arquivo and arquivo.filename:
            os.makedirs(PASTA_DOCUMENTOS, exist_ok=True)
            seguro = re.sub(r"[^\w.\-]+", "_", arquivo.filename).strip("_")[:80]
            caminho = os.path.join(PASTA_DOCUMENTOS, f"{doc.id}-{seguro}")
            with open(caminho, "wb") as f:
                f.write(await arquivo.read())
            doc.caminho_local = os.path.relpath(caminho, PASTA_DADOS)
        if not doc.validade and doc.caminho_local:
            sugerida = validades_mod.sugerir_validade(doc.caminho_local)
            if sugerida:
                doc.validade = sugerida
                d, m, a = sugerida.split("-")[::-1]
                aviso = (f"Validade {d}/{m}/{a} lida do PDF — confira no "
                         "documento antes de confiar.")
        s.commit()
        destino = "/documentos" + (f"?aviso={quote(aviso)}" if aviso else "")
        return RedirectResponse(destino, status_code=303)
    finally:
        s.close()


def _data_ou_nada(texto):
    """Aceita só AAAA-MM-DD real (o campo é <input type=date>, mas quem
    digita à mão merece a mesma proteção do resto do app)."""
    texto = (texto or "").strip()
    try:
        datetime.strptime(texto, "%Y-%m-%d")
        return texto
    except ValueError:
        return None


@app.post("/documentos/{doc_id}/salvar")
async def documento_salvar(request: Request, doc_id: int,
                           nome: str = Form(""), tipo: str = Form(""),
                           validade: str = Form(""),
                           observacao: str = Form("")):
    s = Sessao()
    try:
        doc = s.get(DocumentoEmpresa, doc_id)
        if doc:
            doc.nome = (nome or doc.nome).strip()[:120]
            doc.tipo = (tipo or doc.tipo).strip()[:60]
            nova = _data_ou_nada(validade)
            if nova != doc.validade:
                doc.validade = nova
                doc.ultimo_aviso_dias = None   # validade nova recomeça os avisos
            doc.observacao = (observacao or "").strip()[:2000]
            s.commit()
        return RedirectResponse("/documentos", status_code=303)
    finally:
        s.close()


@app.post("/documentos/{doc_id}/arquivar")
async def documento_arquivar(request: Request, doc_id: int):
    s = Sessao()
    try:
        doc = s.get(DocumentoEmpresa, doc_id)
        if doc:
            doc.arquivado = not doc.arquivado
            s.commit()
        return RedirectResponse("/documentos", status_code=303)
    finally:
        s.close()


@app.get("/documentos/{doc_id}/arquivo")
async def documento_arquivo(request: Request, doc_id: int):
    s = Sessao()
    try:
        doc = s.get(DocumentoEmpresa, doc_id)
        caminho = (os.path.join(PASTA_DADOS, doc.caminho_local)
                   if doc and doc.caminho_local else "")
        if not (caminho and os.path.exists(caminho)):
            return HTMLResponse("Arquivo não encontrado.", status_code=404)
        return FileResponse(caminho, filename=os.path.basename(caminho))
    finally:
        s.close()


@app.get("/logs", response_class=HTMLResponse)
async def logs_coletas(request: Request):
    s = Sessao()
    try:
        registros = (s.query(ColetaLog)
                     .order_by(ColetaLog.inicio.desc()).limit(60).all())
        # Custo de IA visível desde o dia 1 (arquitetura §7) — só ao admin.
        custo_ia = fichas = None
        if _sou_admin(request):
            from ia.cliente import custo_total
            custo_ia = custo_total()
            fichas = s.query(EditalFicha).filter(
                EditalFicha.ficha_json != "").count()
        return templates.TemplateResponse(request, "logs.html",
                                          {"registros": registros,
                                           "custo_ia": custo_ia,
                                           "fichas": fichas})
    finally:
        s.close()


# --------------------------------------------------------------------- config
@app.get("/config", response_class=HTMLResponse)
async def config_form(request: Request, salvo: int = 0):
    if not _sou_admin(request):
        return RedirectResponse("/", status_code=303)
    from .pecas.minutas import dados_empresa
    s = Sessao()
    try:
        empresa = dados_empresa(s)
        return templates.TemplateResponse(request, "config.html", {
            "valores": envcfg.valores_para_tela(), "salvo": salvo,
            "resultado_teste": None, "empresa": empresa,
        })
    finally:
        s.close()


@app.post("/config")
async def config_salvar(request: Request):
    if not _sou_admin(request):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    envcfg.salvar(dict(form))
    # Reagenda a coleta com o novo horário, sem reiniciar. O job de alertas
    # é de intervalo fixo: quem manda na hora é cada perfil.
    agendador.reschedule_job("coleta", trigger="cron", **_gatilho_coleta())
    return RedirectResponse("/config?salvo=1", status_code=303)


@app.post("/config/testar", response_class=HTMLResponse)
def config_testar(request: Request, canal: str = Form("telegram")):
    """Botão 'Enviar mensagem de teste' (SPEC §7)."""
    texto = ("📡 Licerta — mensagem de teste.\n"
             "Se você recebeu isto, o canal está configurado corretamente. ✅")
    if canal == "email":
        ok = alerta_mod.enviar_email(texto)
    else:
        ok = alerta_mod.enviar_telegram(texto)
    cor = "text-green-700" if ok else "text-red-700"
    msg = ("✔ Teste enviado — confira se chegou." if ok else
           "✖ Falhou. Confira os dados e veja o terminal para detalhes.")
    return HTMLResponse(f'<span class="{cor} text-sm font-semibold">{msg}</span>')


# --------------------------------------------------- minha conta e notificações
def _resposta_html(ok, msg_ok, msg_erro):
    cor = "text-green-700" if ok else "text-red-700"
    return HTMLResponse(f'<span class="{cor} text-sm font-semibold">'
                        f'{escape(msg_ok if ok else msg_erro)}</span>')


@app.get("/conta", response_class=HTMLResponse)
def conta(request: Request, bemvindo: int = 0, salvo: int = 0):
    s = Sessao()
    try:
        usuario = s.get(Usuario, eu(request).id)
        aparelhos = len(usuario.assinaturas_push)
        return templates.TemplateResponse(request, "conta.html", {
            "usuario": usuario, "aparelhos_push": aparelhos,
            "bemvindo": bemvindo, "salvo": salvo,
            "bot": _nome_do_bot(),
            "tem_bot": bool(config.TELEGRAM_BOT_TOKEN),
        })
    finally:
        s.close()


@app.post("/conta")
async def conta_salvar(request: Request):
    form = await request.form()
    s = Sessao()
    try:
        usuario = s.get(Usuario, eu(request).id)
        usuario.nome = form.get("nome", usuario.nome).strip() or usuario.nome
        email_alertas = form.get("email_alertas", "").strip()
        usuario.email_alertas = email_alertas if "@" in email_alertas else ""
        usuario.receber_telegram = form.get("receber_telegram") == "on"
        usuario.receber_email = form.get("receber_email") == "on"
        usuario.receber_push = form.get("receber_push") == "on"
        s.commit()
        return RedirectResponse("/conta?salvo=1", status_code=303)
    finally:
        s.close()


@app.post("/conta/senha", response_class=HTMLResponse)
def conta_trocar_senha(request: Request, atual: str = Form(""),
                       nova: str = Form("")):
    s = Sessao()
    try:
        usuario = s.get(Usuario, eu(request).id)
        if not usuarios_mod.conferir_senha(atual, usuario.senha_hash):
            return _resposta_html(False, "", "A senha atual não confere.")
        if len(nova) < 6:
            return _resposta_html(False, "",
                                  "A nova senha precisa de 6+ caracteres.")
        usuario.senha_hash = usuarios_mod.gerar_hash(nova)
        s.commit()
        # trocar a senha derruba as sessões antigas; renova a deste aparelho
        resposta = _resposta_html(True, "Senha trocada. As sessões antigas "
                                        "foram encerradas.", "")
        resposta.set_cookie(
            "sessao", usuarios_mod.criar_token(usuario, _segredo_sessao()),
            httponly=True, samesite="lax", secure=config.COOKIE_SEGURO,
            max_age=usuarios_mod.VALIDADE_SESSAO)
        return resposta
    finally:
        s.close()


_nome_bot_cache = {"nome": "", "quando": 0.0}


def _nome_do_bot():
    """@usuario do bot do Telegram desta instalação (para o link Conectar)."""
    if not config.TELEGRAM_BOT_TOKEN:
        return ""
    if _nome_bot_cache["nome"] and \
            time.monotonic() - _nome_bot_cache["quando"] < 3600:
        return _nome_bot_cache["nome"]
    try:
        import requests as req
        r = req.get("https://api.telegram.org/bot"
                    f"{config.TELEGRAM_BOT_TOKEN}/getMe", timeout=15)
        nome = (r.json().get("result") or {}).get("username", "")
        if nome:
            _nome_bot_cache.update(nome=nome, quando=time.monotonic())
        return nome
    except Exception:  # noqa: BLE001
        return _nome_bot_cache["nome"]


@app.post("/conta/telegram/conectar", response_class=HTMLResponse)
def telegram_conectar(request: Request):
    """Gera o código de pareamento e mostra o link do bot.

    Fluxo de dois toques, como nos apps grandes: o usuário abre o link, o
    Telegram já leva o código junto, ele aperta COMEÇAR e volta para
    confirmar. Ninguém precisa descobrir chat_id na mão.
    """
    bot = _nome_do_bot()
    if not bot:
        return _resposta_html(False, "", "O administrador ainda não "
                              "configurou o bot do Telegram desta instalação.")
    s = Sessao()
    try:
        usuario = s.get(Usuario, eu(request).id)
        usuario.telegram_codigo = secrets.token_hex(8)
        s.commit()
        link = f"https://t.me/{bot}?start={usuario.telegram_codigo}"
        return HTMLResponse(
            f'<div class="text-sm space-y-2">'
            f'<p>1. <a href="{escape(link)}" target="_blank" '
            f'class="text-blue-700 underline font-semibold">Toque aqui para '
            f'abrir o bot @{escape(bot)}</a> e aperte <b>COMEÇAR</b> '
            f'(ou INICIAR).</p>'
            f'<p>2. Depois volte e '
            f'<button hx-post="/conta/telegram/confirmar" '
            f'hx-target="#resTelegram" '
            f'class="border border-blue-700 text-blue-700 px-3 py-1 rounded-lg '
            f'font-semibold hover:bg-blue-50">confirme a conexão</button></p>'
            f"</div>")
    finally:
        s.close()


@app.post("/conta/telegram/confirmar", response_class=HTMLResponse)
def telegram_confirmar(request: Request):
    """Procura nas mensagens recentes do bot o /start com o código gerado."""
    s = Sessao()
    try:
        usuario = s.get(Usuario, eu(request).id)
        if not usuario.telegram_codigo:
            return _resposta_html(False, "", "Toque antes em Conectar.")
        try:
            import requests as req
            r = req.get("https://api.telegram.org/bot"
                        f"{config.TELEGRAM_BOT_TOKEN}/getUpdates",
                        params={"limit": 100}, timeout=20)
            atualizacoes = r.json().get("result") or []
        except Exception:  # noqa: BLE001
            return _resposta_html(False, "", "Não consegui falar com o "
                                             "Telegram. Tente de novo.")
        for a in reversed(atualizacoes):
            msg = a.get("message") or {}
            if (msg.get("text") or "").strip() == \
                    f"/start {usuario.telegram_codigo}":
                usuario.telegram_chat_id = str(msg["chat"]["id"])
                usuario.telegram_codigo = ""
                s.commit()
                alerta_mod.enviar_telegram(
                    "✅ Pronto! Seus alertas da Licerta vão chegar aqui.",
                    chat_id=usuario.telegram_chat_id)
                return _resposta_html(True, "Conectado! Mandei uma mensagem "
                                            "de boas-vindas no seu Telegram.",
                                      "")
        return _resposta_html(False, "", 'Ainda não vi o seu COMEÇAR. Abra o '
                                         'link do passo 1, aperte o botão e '
                                         'tente confirmar de novo.')
    finally:
        s.close()


@app.post("/conta/telegram/desconectar", response_class=HTMLResponse)
def telegram_desconectar(request: Request):
    s = Sessao()
    try:
        usuario = s.get(Usuario, eu(request).id)
        usuario.telegram_chat_id = ""
        s.commit()
        return _resposta_html(True, "Telegram desconectado desta conta.", "")
    finally:
        s.close()


@app.post("/conta/testar/{canal}", response_class=HTMLResponse)
def conta_testar(request: Request, canal: str):
    """Teste dos MEUS canais — cada usuário confere os seus."""
    s = Sessao()
    try:
        usuario = s.get(Usuario, eu(request).id)
        texto = ("📡 Licerta — teste dos seus alertas.\n"
                 "Se chegou, este canal está pronto. ✅")
        if canal == "telegram":
            if not usuario.telegram_chat_id:
                return _resposta_html(False, "", "Conecte o Telegram antes.")
            ok = alerta_mod.enviar_telegram(texto,
                                            chat_id=usuario.telegram_chat_id)
            return _resposta_html(ok, "Teste enviado no seu Telegram.",
                                  "Falhou — tente reconectar.")
        if canal == "email":
            if not usuario.email_alertas:
                return _resposta_html(False, "", "Preencha o e-mail e salve.")
            ok = alerta_mod.enviar_email(texto, destino=usuario.email_alertas)
            return _resposta_html(ok, "Teste enviado no seu e-mail.",
                                  "Falhou — nesta hospedagem o e-mail pode "
                                  "sair só pela rotina diária.")
        if canal == "push":
            entregues = push_mod.enviar_push(
                s, usuario, "📡 Licerta",
                "Teste: os avisos no aparelho estão funcionando ✅", url="/")
            return _resposta_html(entregues > 0,
                                  f"Enviado para {entregues} aparelho(s).",
                                  "Nenhum aparelho ativado ainda — toque em "
                                  "Ativar neste aparelho.")
        return _resposta_html(False, "", "Canal desconhecido.")
    finally:
        s.close()


# --------------------------------------------------------- push (Web Push/PWA)
@app.get("/api/push/chave")
async def push_chave():
    return {"chave": push_mod.chave_publica()}


@app.post("/api/push/assinar")
async def push_assinar(request: Request):
    dados = await request.json()
    endpoint = (dados.get("endpoint") or "")[:2000]
    chaves = dados.get("keys") or {}
    if not (endpoint.startswith("https://") and chaves.get("p256dh")
            and chaves.get("auth")):
        return Response(status_code=400)
    s = Sessao()
    try:
        existente = (s.query(PushAssinatura)
                     .filter_by(endpoint=endpoint).first())
        if existente:
            existente.usuario_id = eu(request).id
            existente.p256dh = chaves["p256dh"]
            existente.auth = chaves["auth"]
        else:
            s.add(PushAssinatura(
                usuario_id=eu(request).id, endpoint=endpoint,
                p256dh=chaves["p256dh"], auth=chaves["auth"],
                rotulo=(request.headers.get("user-agent") or "")[:120]))
        s.commit()
        return {"ok": True}
    finally:
        s.close()


@app.post("/api/push/remover")
async def push_remover(request: Request):
    dados = await request.json()
    s = Sessao()
    try:
        (s.query(PushAssinatura)
         .filter_by(endpoint=dados.get("endpoint", ""),
                    usuario_id=eu(request).id).delete())
        s.commit()
        return {"ok": True}
    finally:
        s.close()


@app.get("/sw.js")
async def service_worker():
    """O service worker precisa ser servido da raiz para valer no site todo."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "static",
                                     "sw.js"), media_type="text/javascript")


@app.get("/manifest.json")
async def manifest():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static",
                                     "manifest.json"),
                        media_type="application/manifest+json")


# ------------------------------------------------------------ usuários (admin)
def _sou_admin(request):
    return eu(request).papel == "admin"


@app.get("/usuarios", response_class=HTMLResponse)
async def usuarios_lista(request: Request, erro: str = ""):
    if not _sou_admin(request):
        return RedirectResponse("/", status_code=303)
    s = Sessao()
    try:
        lista = s.query(Usuario).order_by(Usuario.nome).all()
        return templates.TemplateResponse(request, "usuarios.html", {
            "lista": lista, "erro": erro, "meu_id": eu(request).id})
    finally:
        s.close()


@app.post("/usuarios/criar")
async def usuarios_criar(request: Request, nome: str = Form(""),
                         email: str = Form(""), senha: str = Form(""),
                         papel: str = Form("usuario")):
    if not _sou_admin(request):
        return RedirectResponse("/", status_code=303)
    nome, email = nome.strip(), email.strip().lower()
    if not (nome and "@" in email and len(senha) >= 6):
        return RedirectResponse(
            "/usuarios?erro=Preencha nome, e-mail e senha (6+).",
            status_code=303)
    s = Sessao()
    try:
        if s.query(Usuario).filter_by(email=email).first():
            return RedirectResponse("/usuarios?erro=Este e-mail já tem conta.",
                                    status_code=303)
        s.add(Usuario(nome=nome, email=email, email_alertas=email,
                      papel="admin" if papel == "admin" else "usuario",
                      senha_hash=usuarios_mod.gerar_hash(senha)))
        s.commit()
        return RedirectResponse("/usuarios", status_code=303)
    finally:
        s.close()


@app.post("/usuarios/{usuario_id}/toggle")
async def usuarios_toggle(request: Request, usuario_id: int):
    if not _sou_admin(request):
        return RedirectResponse("/", status_code=303)
    s = Sessao()
    try:
        alvo = s.get(Usuario, usuario_id)
        if alvo and alvo.id != eu(request).id:   # ninguém se desativa sozinho
            alvo.ativo = not alvo.ativo
            s.commit()
        return RedirectResponse("/usuarios", status_code=303)
    finally:
        s.close()


@app.post("/usuarios/{usuario_id}/senha")
async def usuarios_resetar_senha(request: Request, usuario_id: int,
                                 nova: str = Form("")):
    if not _sou_admin(request):
        return RedirectResponse("/", status_code=303)
    if len(nova) < 6:
        return RedirectResponse("/usuarios?erro=Senha nova precisa de 6+.",
                                status_code=303)
    s = Sessao()
    try:
        alvo = s.get(Usuario, usuario_id)
        if alvo:
            alvo.senha_hash = usuarios_mod.gerar_hash(nova)
            s.commit()
        return RedirectResponse("/usuarios", status_code=303)
    finally:
        s.close()


# ------------------------------------------------------------------- execução
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
