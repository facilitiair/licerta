#!/usr/bin/env python
"""
ecd_parser.py — leitura pericial de arquivo ECD (SPED Contábil, .txt pipe-delimitado).

Uso:
  python ia/ferramentas/ecd_parser.py <arquivo.txt> [--out <prefixo_saida>]

Produz no stdout (e, com --out, em arquivos <prefixo>_*.csv):
  1. cabeçalho (0000): CNPJ, período, versão do leiaute
  2. contagem de registros por tipo
  3. plano de contas (I050)
  4. saldos e movimentação por conta (I155) + teste de fechamento por conta
  5. lançamentos (I200/I250) + teste débito = crédito por lançamento
  6. balanço (J100) e DRE (J150) conforme o próprio arquivo
  7. signatários (J930)
  8. sinais para triagem: contas de sinal invertido, concentração mensal, duplicidades

AVISO PERICIAL: as posições de campo abaixo seguem o leiaute usual da ECD.
Confirmar contra o Manual de Orientação do Leiaute da versão indicada no 0000
antes de reportar qualquer divergência. Divergência de leiaute é falso positivo
de ferramenta, não achado. Somente leitura — nunca altera o arquivo de entrada.
"""
import sys, csv, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

def dec(s):
    s = (s or "").strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(s) if s else Decimal(0)
    except InvalidOperation:
        return Decimal(0)

def signed(valor, ind):
    """Saldo com sinal: devedor positivo, credor negativo."""
    return valor if (ind or "").upper() == "D" else -valor

def read_ecd(path):
    regs = defaultdict(list)
    with open(path, "r", encoding="latin-1", errors="replace") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.startswith("|"):
                continue
            campos = line.split("|")[1:-1]
            if campos:
                regs[campos[0]].append((n, campos))
    return regs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--out", help="prefixo dos CSV de saída")
    a = ap.parse_args()
    regs = read_ecd(a.arquivo)
    out = a.out
    writers = {}

    def emit(nome, header, rows):
        print(f"\n=== {nome} ({len(rows)} linhas) ===")
        print(" | ".join(header))
        for r in rows[:50]:
            print(" | ".join(str(x) for x in r))
        if len(rows) > 50:
            print(f"... ({len(rows)-50} linhas omitidas no stdout; íntegras no CSV)")
        if out:
            with open(f"{out}_{nome}.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(header); w.writerows(rows)

    # 1. cabeçalho
    print("=== 0000 — cabeçalho ===")
    for n, c in regs.get("0000", []):
        print(f"linha {n}: " + " | ".join(c))
    # 2. contagem
    print("\n=== contagem de registros por tipo ===")
    for k in sorted(regs):
        print(f"{k}: {len(regs[k])}")

    # 3. plano de contas I050: REG|DT_ALT|COD_NAT|IND_CTA|NIVEL|COD_CTA|COD_CTA_SUP|CTA
    plano = {}
    rows = []
    for n, c in regs.get("I050", []):
        c += [""] * (8 - len(c))
        plano[c[5]] = {"nat": c[2], "tipo": c[3], "nivel": c[4], "sup": c[6], "nome": c[7]}
        rows.append([n, c[5], c[2], c[3], c[4], c[6], c[7]])
    emit("I050_plano", ["linha", "cod_cta", "cod_nat", "ind_cta", "nivel", "cta_sup", "nome"], rows)

    # 4. saldos I155: REG|COD_CTA|COD_CCUS|VL_SLD_INI|IND_DC_INI|VL_DEB|VL_CRED|VL_SLD_FIN|IND_DC_FIN
    rows, nao_fecha, invertidos = [], [], []
    saldo_final = defaultdict(Decimal)
    for n, c in regs.get("I155", []):
        c += [""] * (9 - len(c))
        ini = signed(dec(c[3]), c[4]); deb = dec(c[5]); cred = dec(c[6]); fim = signed(dec(c[7]), c[8])
        calc = ini + deb - cred
        ok = (calc == fim)
        if not ok:
            nao_fecha.append([n, c[1], ini, deb, cred, fim, calc, calc - fim])
        saldo_final[c[1]] += fim
        nat = plano.get(c[1], {}).get("nat", "")
        # natureza 01 ativo (devedor), 02 passivo, 03 PL (credores), 04 resultado
        if (nat == "01" and fim < 0) or (nat in ("02", "03") and fim > 0):
            invertidos.append([n, c[1], nat, plano.get(c[1], {}).get("nome", ""), fim])
        rows.append([n, c[1], c[2], ini, deb, cred, fim, "ok" if ok else "NAO_FECHA"])
    emit("I155_saldos", ["linha", "cod_cta", "ccus", "sld_ini", "deb", "cred", "sld_fin", "teste"], rows)
    emit("teste_fechamento_conta", ["linha", "cod_cta", "ini", "deb", "cred", "fim_declarado", "fim_calculado", "diferenca"], nao_fecha)
    emit("triagem_sinal_invertido", ["linha", "cod_cta", "nat", "nome", "saldo_final"], invertidos)

    # 5. lançamentos I200: REG|NUM_LCTO|DT_LCTO|VL_LCTO|IND_LCTO ; I250: REG|COD_CTA|COD_CCUS|VL_DC|IND_DC|NUM_ARQ|COD_HIST_PAD|HIST|COD_PART
    # I250 vem logo após seu I200 no arquivo: reconstruir pela ordem de linha.
    lanc, partidas = [], []
    seq = sorted(regs.get("I200", []) + regs.get("I250", []), key=lambda t: t[0])
    atual = None
    por_mes = Counter()
    dup = Counter()
    for n, c in seq:
        if c[0] == "I200":
            c += [""] * (5 - len(c))
            atual = {"linha": n, "num": c[1], "data": c[2], "valor": dec(c[3]), "tipo": c[4], "deb": Decimal(0), "cred": Decimal(0), "contas": []}
            lanc.append(atual)
            if len(c[2]) == 8:
                por_mes[c[2][4:8] + "-" + c[2][2:4]] += 1
        elif c[0] == "I250" and atual is not None:
            c += [""] * (9 - len(c))
            v = dec(c[3]); ind = c[4].upper()
            if ind == "D": atual["deb"] += v
            else: atual["cred"] += v
            atual["contas"].append(c[1])
            partidas.append([n, atual["num"], atual["data"], c[1], v, ind, c[7]])
            dup[(atual["data"], c[1], v, ind)] += 1
    desbal = [[l["linha"], l["num"], l["data"], l["valor"], l["deb"], l["cred"], l["deb"] - l["cred"]] for l in lanc if l["deb"] != l["cred"]]
    emit("I250_partidas", ["linha", "num_lcto", "data", "cod_cta", "valor", "d_c", "historico"], partidas)
    emit("teste_lancamento_desbalanceado", ["linha", "num_lcto", "data", "vl_lcto", "soma_deb", "soma_cred", "diferenca"], desbal)
    emit("triagem_concentracao_mensal", ["mes", "qtd_lancamentos"], sorted(por_mes.items()))
    emit("triagem_duplicidade", ["data", "cod_cta", "valor", "d_c", "ocorrencias"], [list(k) + [v] for k, v in dup.items() if v > 1])

    # 6. J100 balanço: REG|COD_AGL|IND_COD_AGL|NIVEL_AGL|COD_AGL_SUP|IND_GRP_BAL|DESCR_COD_AGL|VL_CTA|IND_DC_CTA|...
    rows = []
    for n, c in regs.get("J100", []):
        c += [""] * (9 - len(c))
        rows.append([n, c[1], c[3], c[5], c[6], dec(c[7]), c[8]])
    emit("J100_balanco", ["linha", "cod_agl", "nivel", "grupo", "descricao", "valor", "d_c"], rows)
    # J150 DRE: REG|NU_ORDEM|COD_AGL|IND_COD_AGL|NIVEL_AGL|COD_AGL_SUP|DESCR_COD_AGL|VL_CTA|IND_VL|... (posições variam por versão)
    rows = [[n] + c[1:] for n, c in regs.get("J150", [])]
    emit("J150_dre_bruto", ["linha", "campos..."], rows)
    # 7. J930 signatários
    rows = [[n] + c[1:] for n, c in regs.get("J930", [])]
    emit("J930_signatarios", ["linha", "campos..."], rows)

    # 8. síntese
    print("\n=== SÍNTESE (triagem — não é achado) ===")
    print(f"contas com fechamento divergente: {len(nao_fecha)}")
    print(f"lançamentos desbalanceados: {len(desbal)}")
    print(f"contas com saldo de sinal invertido: {len(invertidos)}")
    print(f"meses com lançamento: {len(por_mes)} de 12; máximo em um mês: {max(por_mes.values()) if por_mes else 0}")
    print(f"combinações (data, conta, valor, D/C) repetidas: {sum(1 for v in dup.values() if v > 1)}")
    print("Conferir posições de campo contra o leiaute da versão indicada no 0000 antes de reportar.")

if __name__ == "__main__":
    main()
