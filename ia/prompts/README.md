# Biblioteca de prompts da plataforma

Cada arquivo é um prompt autossuficiente, enviado à API do LLM por
`ia/cliente.py` junto com as **entradas** declaradas no topo (dossiê da
empresa cliente, ficha do edital, documentos do caso...). Nada de nenhuma
empresa está no texto: o cliente entra sempre como dado.

| Prompt | Módulo (arquitetura) | Camada de IA |
|---|---|---|
| `analise-edital.md` | editais/ — gera a ficha do edital | 2 · extração (1× por versão, global) |
| `identificacao-riscos.md` | editais/ — cláusulas restritivas e armadilhas | 2 · extração |
| `checagem-habilitacao.md` | documentos/ — exigências × dossiê do cliente | 3 · sob demanda |
| `montagem-proposta.md` | documentos/ — checklist e estrutura de envio | 3 · sob demanda |
| `analise-planilha-concorrente.md` | pecas/ — perícia de proposta de preços | 3 · sob demanda |
| `redacao-impugnacao.md` | pecas/ — minuta (sempre marcada como minuta) | 3 · sob demanda |
| `redacao-recurso.md` | pecas/ — minuta | 3 · sob demanda |
| `redacao-contrarrazoes.md` | pecas/ — minuta | 3 · sob demanda |
| `consulta-juridica.md` | conteudo/ — tutor e hub das regras periciais | 3 · sob demanda |
| `gestao-dossie.md` | documentos/ — esquema e atualização do dossiê | 3 · sob demanda |
| `peritos/perito-contabil.md` | documentos/pecas — perícia econômico-financeira | 3 · sob demanda |
| `peritos/perito-atestados.md` | documentos/pecas — perícia de qualificação técnica | 3 · sob demanda |
| `peritos/leitor-caderno.md` | documentos/ — extração estruturada de lotes de PDF | 2 · extração |
| `peritos/conferente-pre-envio.md` | documentos/ — portão final antes do envio | 3 · sob demanda |
| `peritos/perito-corretor.md` | analista/ — aplica as correções do revisor ao parecer/laudo, sem reabrir o mérito | 3 · sob demanda |

Apoio em `ia/referencias/` (consumido como `{{base_juridica}}`):
`lei-14133-2021.md`, `jurisprudencia.md`, `glossario.md`,
`contabilidade-habilitacao.md`, `base-normativa-contabil.md`.
Ferramenta determinística em `ia/ferramentas/ecd_parser.py` (parse de
ECD/SPED — código calcula, LLM interpreta a saída).

Regra de manutenção: prompt se edita AQUI, versionado no git — nunca inline
no código. Busca e matching de licitações não usam LLM (são código puro em
`app/`).
