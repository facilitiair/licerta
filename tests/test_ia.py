"""Camada de IA: custo logado, prompts versionados e saída estrita."""
import json

from ia import camadas, cliente


def test_custo_por_modelo_e_calculado_certo():
    assert camadas.custo_usd("claude-sonnet-5", 1_000_000, 0) == 3.00
    assert camadas.custo_usd("claude-sonnet-5", 0, 1_000_000) == 15.00
    assert camadas.custo_usd("modelo-desconhecido", 999, 999) == 0.0


def test_sem_chave_de_api_o_erro_e_claro_e_nada_explode(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        cliente.chamar("teste", "sistema", "oi")
        assert False, "devia ter recusado sem a chave"
    except RuntimeError as e:
        assert "ANTHROPIC_API_KEY" in str(e)


def test_extrair_json_aceita_cerca_de_codigo():
    bruto = 'Aqui está:\n```json\n{"a": 1}\n```\nEspero ter ajudado!'
    assert json.loads(cliente._extrair_json(bruto)) == {"a": 1}
    assert json.loads(cliente._extrair_json('{"b": 2}')) == {"b": 2}


def test_registro_de_custo_vai_para_o_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(cliente, "CAMINHO_CUSTOS",
                        str(tmp_path / "custos.jsonl"))
    cliente._registrar_custo("analisar_edital", "claude-sonnet-5",
                             10_000, 2_000, 3.2)
    linha = json.loads((tmp_path / "custos.jsonl").read_text("utf-8"))
    assert linha["job"] == "analisar_edital"
    assert linha["custo_usd"] == round((10_000 * 3 + 2_000 * 15) / 1e6, 6)
    assert cliente.custo_total() >= 0                  # nunca explode
