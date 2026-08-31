"""O radar vigia a si mesmo (arquitetura, princípio 4).

Falha silenciosa é o pior defeito possível deste produto: quem confia nos
alertas para de olhar o painel — se a coleta morrer sem barulho, a pessoa
perde pregão sem saber que perdeu. Este módulo detecta os jeitos conhecidos
de morrer em silêncio e avisa os ADMINISTRADORES pelos canais deles.

Regras da casa:
- Só código determinístico sobre o que o banco registra. Nada de IA aqui.
- O vigia nunca conserta nada sozinho: detecta, explica e aponta /logs.
- Anti-fadiga: avisa quando o problema surge, relembra no máximo uma vez
  por dia enquanto durar, e manda o "resolvido" quando passar. Estado em
  `vigia_problemas` — some da tabela = está saudável.
"""
import logging
from datetime import timedelta

import requests

from .config import agora, config
from .db import (ColetaLog, Licitacao, PerfilBusca, Sessao, Usuario,
                 VigiaProblema)

log = logging.getLogger("radar.vigia")

# Enquanto um problema durar, o lembrete sai no máximo nesta cadência.
RELEMBRAR_APOS = timedelta(hours=24)

# Hora em que ESTE processo subiu. Serve de carência: logo depois de ligar
# o app (o PC ficou dias desligado, ou houve deploy), uma coleta "velha" é
# normal — o cron ainda vai chegar lá. Sem a carência, todo boot avisaria
# um problema que se resolve sozinho em minutos.
INICIO_PROCESSO = agora()


# ------------------------------------------------------------- diagnósticos
# Cada checagem é função pura sobre dados simples — testável sem banco.

def checar_coleta_parada(ultimo_ok, tem_perfil_ativo, agora_, inicio_processo,
                         passo_horas):
    """A coleta simplesmente não roda (agendador morto, processo travado).

    `ultimo_ok` é o fim da última coleta concluída com sucesso. O limite é
    dois ciclos perdidos: um só pode ser azar (deploy no meio, rede fraca).
    """
    if not tem_perfil_ativo:
        return None            # sem perfil não há o que coletar; o painel guia
    if agora_ - inicio_processo < timedelta(hours=passo_horas):
        return None            # acabou de subir: o cron ainda vai chegar
    limite = timedelta(hours=max(2 * passo_horas, 6))
    atraso = agora_ - (ultimo_ok or inicio_processo)
    if atraso <= limite:
        return None
    horas = int(atraso.total_seconds() // 3600)
    return {"chave": "coleta_parada",
            "titulo": f"A coleta não conclui com sucesso há {horas}h",
            "detalhe": ("Nenhuma coleta bem-sucedida desde "
                        + (ultimo_ok.strftime("%d/%m %H:%M") if ultimo_ok
                           else "que o app subiu")
                        + f" (o normal é a cada {passo_horas}h). "
                        "Veja os registros em /logs.")}


def checar_coleta_falhando(ultimas):
    """Coletas concluídas terminando em erro, em sequência.

    `ultimas` vem ordenada da mais recente para a mais antiga. Uma falha
    isolada não vira aviso — a fonte engasga e o ciclo seguinte resolve.
    Coleta interrompida por reinício do app não entra na conta: não é a
    fonte falhando, é o processo indo embora (comum num PC que liga e
    desliga); se os reinícios impedirem qualquer coleta de concluir, quem
    acusa é o `coleta_parada`.
    """
    from .radar.coleta import MSG_INTERROMPIDA
    seguidas = []
    for c in ultimas:
        if c.sucesso:
            break
        if (c.detalhe_erro or "").strip() == MSG_INTERROMPIDA:
            continue
        seguidas.append(c)
    if len(seguidas) < 2:
        return None
    linhas = (seguidas[0].detalhe_erro or "").strip().splitlines()
    resumo = linhas[0][:200] if linhas else "sem detalhe registrado"
    return {"chave": "coleta_falhando",
            "titulo": f"A coleta falhou {len(seguidas)} vezes seguidas",
            "detalhe": f"Último erro: {resumo} — o histórico está em /logs."}


def checar_captura_zerada(ultimas, frescas_24h, agora_):
    """Coleta 'bem-sucedida' que não escreve NADA no banco.

    É o disfarce clássico de fonte quebrada: um WAF novo ou uma mudança de
    formato na API devolve lista vazia com HTTP 200, o log diz sucesso e o
    radar fica cego sem nenhum erro em lugar algum. Como a coleta reescreve
    `coletado_em` de toda licitação aberta que encontra, um dia inteiro sem
    tocar em linha alguma é fortíssimo sinal de fonte muda.
    """
    corte = agora_ - timedelta(hours=24)
    ok_24h = [c for c in ultimas if c.sucesso and c.fim and c.fim >= corte]
    if len(ok_24h) < 2 or frescas_24h > 0:
        return None
    return {"chave": "captura_zerada",
            "titulo": "As coletas dizem sucesso, mas não trazem dado nenhum",
            "detalhe": (f"{len(ok_24h)} coletas concluíram bem nas últimas 24h "
                        "e nenhuma licitação foi gravada ou atualizada. "
                        "Pode ser mudança na API do PNCP ou um recorte de "
                        "perfil que não devolve nada.")}


def checar_alertas_travados(perfis, agora_, inicio_processo):
    """Alerta que não é despachado há muito mais tempo que a frequência dele.

    Pega tanto o job de alertas morto quanto o canal recusando envio — nos
    dois casos `ultimo_envio` para de andar (um ciclo sem novidade também o
    atualiza, então parado de verdade = ninguém despachou).
    """
    if agora_ - inicio_processo < timedelta(hours=1):
        return None            # após religar, o catch-up resolve em minutos
    limites = {"diario": timedelta(hours=48), "semanal": timedelta(days=8),
               "mensal": timedelta(days=32), "anual": timedelta(days=367)}
    travados = []
    for p in perfis:
        freq = getattr(p, "frequencia", None) or "diario"
        if freq == "horas":
            # A pausa noturna é legítima (hora_envio é o 1º envio do dia):
            # o gap normal chega perto de 24h — o limite precisa passar disso.
            intervalo = getattr(p, "intervalo_horas", 3) or 3
            limite = timedelta(hours=24 + 2 * intervalo)
        else:
            limite = limites.get(freq, timedelta(hours=48))
        ultimo = getattr(p, "ultimo_envio", None) or getattr(p, "criado_em", None)
        if not ultimo or ultimo > agora_:
            continue           # relógio bagunçado já é tratado no despacho
        if agora_ - ultimo > limite:
            travados.append(p.nome)
    if not travados:
        return None
    return {"chave": "alerta_travado",
            "titulo": f"{len(travados)} alerta(s) parados há tempo demais",
            "detalhe": ("Sem despacho nem ciclo vazio nos perfis: "
                        + ", ".join(sorted(travados)[:5])
                        + (" e outros" if len(travados) > 5 else "")
                        + ". Confira os canais de aviso do dono do perfil.")}


def diagnosticar(sessao_db, agora_=None, coletando=None, inicio_processo=None):
    """Roda todas as checagens sobre o banco. Devolve a lista de problemas."""
    agora_ = agora_ or agora()
    inicio = inicio_processo or INICIO_PROCESSO
    if coletando is None:
        from .radar.coleta import coleta_em_andamento
        coletando = coleta_em_andamento()
    ultimas = (sessao_db.query(ColetaLog).filter(ColetaLog.fim.isnot(None))
               .order_by(ColetaLog.fim.desc()).limit(10).all())
    ultimo_ok = next((c.fim for c in ultimas if c.sucesso), None)
    perfis = (sessao_db.query(PerfilBusca).filter_by(ativo=True).all())
    from .sincronizar import PERFIL_SISTEMA
    perfis = [p for p in perfis if p.nome != PERFIL_SISTEMA]
    frescas = (sessao_db.query(Licitacao)
               .filter(Licitacao.coletado_em >= agora_ - timedelta(hours=24))
               .count())
    problemas = []
    if not coletando:      # coleta rodando agora não está "parada"
        problemas.append(checar_coleta_parada(
            ultimo_ok, bool(perfis), agora_, inicio,
            config.HORAS_ENTRE_COLETAS))
    problemas.append(checar_coleta_falhando(ultimas))
    problemas.append(checar_captura_zerada(ultimas, frescas, agora_))
    problemas.append(checar_alertas_travados(
        [p for p in perfis if p.notificar], agora_, inicio))
    return [p for p in problemas if p]


# ------------------------------------------------------------------- aviso
def _montar_mensagem(novos_ou_lembretes, resolvidos):
    partes = ["🩺 Licerta — saúde do radar\n"]
    for p in novos_ou_lembretes:
        partes.append(f"⚠️ {p['titulo']}\n   {p['detalhe']}\n")
    for titulo in resolvidos:
        partes.append(f"✅ Resolvido: {titulo}\n")
    partes.append(f"Registros: {config.APP_URL}/logs")
    return "\n".join(partes)


def _avisar_admins(sessao_db, texto, resumo=""):
    """Melhor esforço pelos canais dos administradores. True se algum chegou.

    Problema de saúde é assunto de quem opera a instalação — não incomoda
    os demais usuários. Instalação antiga sem admin com canal cai nos
    canais globais do .env, como os alertas sempre fizeram.
    """
    from .notificacoes import alerta, push
    chegou = False
    admins = (sessao_db.query(Usuario)
              .filter_by(papel="admin", ativo=True).all())
    for adm in admins:
        if adm.receber_telegram and adm.telegram_chat_id:
            chegou |= alerta.enviar_telegram(texto, chat_id=adm.telegram_chat_id)
        if adm.receber_email and adm.email_alertas:
            chegou |= alerta.enviar_email(texto, destino=adm.email_alertas)
        if adm.receber_push:
            try:
                chegou |= push.enviar_push(
                    sessao_db, adm, "🩺 Saúde do radar",
                    resumo or "O radar precisa da sua atenção — toque para ver",
                    url=config.APP_URL + "/logs") > 0
            except Exception:  # noqa: BLE001 — push nunca derruba o vigia
                log.exception("Push do vigia falhou")
    if not chegou:
        chegou = alerta.enviar_telegram(texto) or alerta.enviar_email(texto)
    return chegou


def avisar_admins(sessao_db, texto, resumo=""):
    """Nome público: outros módulos (validades do dossiê, rotina) também
    avisam os administradores por aqui — operação é assunto de admin.
    Delega (em vez de apelidar) para o monkeypatch de teste valer nos dois."""
    return _avisar_admins(sessao_db, texto, resumo=resumo)


def vigiar(agora_=None, sessao_db=None):
    """Job periódico: diagnostica, compara com o estado anterior e avisa.

    `avisado_em` só é gravado quando algum canal aceitou a mensagem — se
    todos os canais estiverem fora, o vigia tenta de novo no próximo ciclo
    em vez de considerar o dono avisado.
    """
    agora_ = agora_ or agora()
    sessao = sessao_db or Sessao()
    try:
        atuais = {p["chave"]: p for p in diagnosticar(sessao, agora_)}
        registros = {r.chave: r for r in sessao.query(VigiaProblema).all()}
        avisar, resolvidos = [], []
        for chave, prob in atuais.items():
            reg = registros.get(chave)
            if reg is None:
                reg = VigiaProblema(chave=chave, titulo=prob["titulo"],
                                    detalhe=prob["detalhe"], desde=agora_)
                sessao.add(reg)
                avisar.append((reg, prob))
                log.warning("Problema novo: %s", prob["titulo"])
            else:
                reg.titulo, reg.detalhe = prob["titulo"], prob["detalhe"]
                if not reg.avisado_em or agora_ - reg.avisado_em >= RELEMBRAR_APOS:
                    avisar.append((reg, prob))
        for chave, reg in registros.items():
            if chave not in atuais:
                # Só comemora o que chegou a ser avisado; problema que surgiu
                # e sumiu entre dois ciclos nunca virou mensagem.
                if reg.avisado_em:
                    resolvidos.append(reg.titulo)
                sessao.delete(reg)
                log.info("Problema resolvido: %s", reg.titulo)
        sessao.commit()
        if avisar or resolvidos:
            texto = _montar_mensagem([p for _, p in avisar], resolvidos)
            resumo = "; ".join(p["titulo"] for _, p in avisar) or \
                "Problema resolvido: " + "; ".join(resolvidos)
            if _avisar_admins(sessao, texto, resumo=resumo):
                for reg, _ in avisar:
                    reg.avisado_em = agora_
                sessao.commit()
        return list(atuais.values())
    finally:
        if sessao_db is None:
            sessao.close()


# -------------------------------------------------- vigilância de fora
def checar_site_publicado(url, avisar=True):
    """O vigia interno não enxerga o próprio site fora do ar — só alguém de
    fora enxerga. Feita para rodar no GitHub Actions (ou no PC), contra o
    `/api/saude` público. Devolve (ok, detalhe).
    """
    try:
        r = requests.get(url.rstrip("/") + "/api/saude", timeout=30)
        r.raise_for_status()
        dados = r.json()
        ok = dados.get("app") == "licerta"
        detalhe = (f"versão {dados.get('versao')}, "
                   f"{dados.get('problemas', 0)} problema(s) interno(s)")
        if not ok:
            detalhe = f"respondeu, mas não parece o Licerta: {str(dados)[:120]}"
    except Exception as e:  # noqa: BLE001 — fora do ar é justamente o caso
        ok, detalhe = False, f"não respondeu: {e}"
    if not ok and avisar:
        sessao = Sessao()
        try:
            _avisar_admins(
                sessao,
                "🩺 Licerta — o site publicado NÃO está respondendo\n\n"
                f"Endereço: {url}\nDiagnóstico: {detalhe}\n\n"
                "Enquanto isso os alertas do site não saem — confira a "
                "hospedagem (Railway).",
                resumo="O site publicado não está respondendo")
        finally:
            sessao.close()
    return ok, detalhe
