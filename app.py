"""Dashboard local do Radar de Editais.

Uso: python app.py  ->  http://localhost:8765
"""
import subprocess
import sys

from flask import Flask, jsonify, render_template, request
from ruamel.yaml import YAML

from busca_editais import config as cfg_mod
from busca_editais import db as db_mod
from busca_editais.fontes import pncp_busca

app = Flask(__name__)
yaml_rt = YAML()  # round-trip: preserva comentários do config.yaml
yaml_rt.preserve_quotes = True

_coleta = {"proc": None}

STATUS_VALIDOS = {"novo", "visto", "interesse", "descartado"}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/licitacoes")
def listar():
    filtros, params = [], []
    if request.args.get("status"):
        filtros.append("status=?")
        params.append(request.args["status"])
    else:
        filtros.append("status != 'descartado'")
    for campo in ("categoria", "uf", "fonte"):
        if request.args.get(campo):
            filtros.append(f"{campo} LIKE ?")
            params.append(f"%{request.args[campo]}%")
    if request.args.get("q"):
        filtros.append("(objeto LIKE ? OR orgao LIKE ? OR municipio LIKE ?)")
        params.extend([f"%{request.args['q']}%"] * 3)
    where = " AND ".join(filtros) if filtros else "1=1"
    con = db_mod.conectar()
    linhas = con.execute(
        f"SELECT * FROM licitacoes WHERE {where} "
        "ORDER BY CASE WHEN data_encerramento IS NULL THEN 1 "
        "  WHEN replace(data_encerramento,'T',' ') < datetime('now','localtime') THEN 2 "
        "  ELSE 0 END, data_encerramento LIMIT 500", params).fetchall()
    con.close()
    return jsonify([dict(l) for l in linhas])


@app.post("/api/licitacoes/<int:lid>/status")
def mudar_status(lid):
    novo = (request.json or {}).get("status")
    if novo not in STATUS_VALIDOS:
        return jsonify({"erro": "status inválido"}), 400
    con = db_mod.conectar()
    con.execute("UPDATE licitacoes SET status=? WHERE id=?", (novo, lid))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.get("/api/pesquisar")
def pesquisar():
    """Busca livre no PNCP: qualquer palavra, qualquer estado."""
    try:
        resultado = pncp_busca.pesquisar(
            q=request.args.get("q", ""),
            ufs=request.args.get("ufs") or None,
            status=request.args.get("status", "abertas"),
            pagina=int(request.args.get("pagina", 1)),
        )
    except Exception as e:
        return jsonify({"erro": f"PNCP indisponível: {e}"}), 502
    con = db_mod.conectar()
    no_radar = {l["id_fonte"] for l in con.execute(
        "SELECT id_fonte FROM licitacoes WHERE fonte='pncp'")}
    con.close()
    for item in resultado["itens"]:
        item["no_radar"] = item["id_fonte"] in no_radar
    return jsonify(resultado)


@app.post("/api/radar")
def salvar_no_radar():
    """Salva no radar um edital vindo da busca livre."""
    item = request.json or {}
    if not item.get("id_fonte"):
        return jsonify({"erro": "item sem identificador"}), 400
    item.setdefault("fonte", "pncp")
    item["categoria"] = item.get("categoria") or "manual"
    con = db_mod.conectar()
    novo = db_mod.upsert(con, item)
    con.commit()
    con.close()
    return jsonify({"ok": True, "novo": novo})


@app.get("/api/config")
def obter_config():
    return jsonify(cfg_mod.carregar())


@app.post("/api/config")
def salvar_config():
    dados = request.json or {}
    with open(cfg_mod.ARQUIVO_CONFIG, encoding="utf-8") as f:
        doc = yaml_rt.load(f)
    for chave in ("ufs", "municipios", "modalidades", "dias_horizonte",
                  "valor_minimo", "excluir_termos"):
        if chave in dados:
            doc[chave] = dados[chave]
    if "categorias" in dados:
        doc["categorias"] = {n: {"termos": g.get("termos", [])}
                             for n, g in dados["categorias"].items()}
    if "email" in dados:
        for k, v in dados["email"].items():
            doc.setdefault("email", {})[k] = v
    if "tcepi" in dados:
        for k, v in dados["tcepi"].items():
            doc.setdefault("tcepi", {})[k] = v
    with open(cfg_mod.ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
        yaml_rt.dump(doc, f)
    return jsonify({"ok": True})


@app.post("/api/coletar")
def coletar_agora():
    proc = _coleta["proc"]
    if proc and proc.poll() is None:
        return jsonify({"rodando": True})
    _coleta["proc"] = subprocess.Popen(
        [sys.executable, "radar.py", "--sem-email"], cwd=cfg_mod.RAIZ)
    return jsonify({"rodando": True, "iniciada": True})


@app.get("/api/coletar/status")
def coleta_status():
    proc = _coleta["proc"]
    return jsonify({"rodando": bool(proc and proc.poll() is None)})


if __name__ == "__main__":
    porta = (cfg_mod.carregar().get("dashboard") or {}).get("porta", 8765)
    app.run(host="127.0.0.1", port=porta, debug=False)
