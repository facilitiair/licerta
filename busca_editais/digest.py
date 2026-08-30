"""Digest por e-mail das licitações novas que casaram com o perfil."""
import os
import smtplib
from datetime import date
from email.mime.text import MIMEText

from .config import RAIZ


def _fmt_valor(v):
    if v is None:
        return "não informado"
    return "R$ {:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def _html(itens):
    blocos = []
    for it in itens:
        blocos.append(f"""
        <div style="border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin:10px 0;">
          <div style="font-size:12px;color:#666;">
            [{(it['categoria'] or '').upper()}] {it['modalidade'] or ''} —
            {it['municipio'] or ''}/{it['uf'] or ''} — {it['orgao'] or ''}
          </div>
          <div style="margin:6px 0;font-size:14px;"><b>{it['objeto'] or ''}</b></div>
          <div style="font-size:13px;">
            Valor estimado: <b>{_fmt_valor(it['valor_estimado'])}</b> ·
            Propostas até: <b>{it['data_encerramento'] or 'ver edital'}</b> ·
            Fonte: {it['fonte'].upper()}
          </div>
          {f'<a href="{it["link"]}" style="font-size:13px;">Abrir no portal</a>' if it['link'] else ''}
        </div>""")
    return f"""<html><body style="font-family:Segoe UI,Arial,sans-serif;max-width:720px;">
      <h2>Radar de Editais — {date.today().strftime('%d/%m/%Y')}</h2>
      <p>{len(itens)} licitação(ões) nova(s) compatível(is) com o perfil configurado:</p>
      {''.join(blocos)}
      <p style="color:#999;font-size:12px;">Gerado automaticamente pelo Radar de Editais.</p>
    </body></html>"""


def enviar(config, itens, log=print):
    """Envia digest por e-mail; sem SMTP configurado, salva HTML em digests/."""
    if not itens:
        log("  Digest: nada novo para notificar")
        return
    html = _html(itens)
    cfg = dict(config.get("email") or {})
    # No GitHub Actions as credenciais vêm de secrets, não do config.yaml
    if os.environ.get("GMAIL_SENHA_APP"):
        cfg["habilitado"] = True
        cfg["senha_app"] = os.environ["GMAIL_SENHA_APP"]
        cfg["usuario"] = os.environ.get("GMAIL_USUARIO", cfg.get("usuario"))
        if os.environ.get("EMAIL_DESTINATARIOS"):
            cfg["destinatarios"] = os.environ["EMAIL_DESTINATARIOS"].split(",")
    if cfg.get("habilitado") and cfg.get("senha_app"):
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = f"Radar de Editais: {len(itens)} nova(s) — {date.today().strftime('%d/%m/%Y')}"
        msg["From"] = cfg["usuario"]
        msg["To"] = ", ".join(cfg.get("destinatarios") or [cfg["usuario"]])
        with smtplib.SMTP(cfg.get("smtp_host", "smtp.gmail.com"),
                          cfg.get("smtp_porta", 587), timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg["usuario"], cfg["senha_app"])
            smtp.send_message(msg)
        log(f"  Digest: e-mail enviado com {len(itens)} licitações")
    else:
        pasta = os.path.join(RAIZ, "digests")
        os.makedirs(pasta, exist_ok=True)
        arq = os.path.join(pasta, f"digest_{date.today().isoformat()}.html")
        with open(arq, "w", encoding="utf-8") as f:
            f.write(html)
        log(f"  Digest: e-mail desabilitado; salvo em {arq}")
