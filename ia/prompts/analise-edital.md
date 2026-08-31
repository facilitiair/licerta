# Análise de Edital

Este prompt lê um edital de licitação pública (Lei 14.133/2021) com seus anexos e produz um **Resumo Executivo** padronizado: identificação, objeto, valores, datas-chave calculadas em dias úteis, condições de participação, lista completa de documentos de habilitação cruzada contra o dossiê da empresa cliente, exigências de forma da proposta, garantias, critérios de aceitabilidade de preços, riscos preliminares e uma recomendação executiva (participar / participar com ressalvas / não participar).

## Entradas

- `{{edital_texto}}` — texto integral do edital **e de todos os anexos disponíveis** (Termo de Referência / Projeto Básico, planilha orçamentária, minuta de contrato/ata, modelos de declaração). Se algum anexo essencial não vier, a análise é declarada INCOMPLETA.
- `{{ficha_edital}}` — metadados já estruturados do certame: número, modalidade, órgão, objeto resumido, valor estimado, data e hora da sessão pública, portal de origem.
- `{{dossie_empresa}}` — dossiê da empresa cliente: identificação societária, ramo de atuação, CNAEs, responsáveis técnicos e registros em conselho, acervo técnico (atestados e CATs com **objeto, quantitativos, valor, contratante, período e RT**), certidões com respectivas validades, balanços e índices, cadastros, declarações padrão, garantias disponíveis.
- `{{documentos_do_caso}}` — conteúdo dos documentos da empresa efetivamente abertos e lidos nesta análise (certidões, atestados, CATs, balanços, contrato social). O que não estiver aqui **não foi lido** e não pode ser afirmado.
- `{{data_de_hoje}}` — data de referência para todos os cálculos de prazo.
- `{{calendario_feriados}}` — feriados nacionais, estaduais e (quando conhecidos) municipais aplicáveis ao órgão licitante.
- `{{base_juridica}}` — síntese da Lei 14.133/2021, jurisprudência consolidada (TCU/STJ/STF/TCEs) e glossário técnico.

---

## Procedimento

### Passo 1 — verificar se a sessão já ocorreu

Compare a data da sessão pública com `{{data_de_hoje}}` **antes de qualquer análise**. Se a sessão já passou, isso é a **primeira linha da resposta** — o resumo passa a ser material de aprendizado, não de decisão.

### Passo 2 — verificar a completude do material

O edital se lê da primeira à última página, anexos incluídos. Se faltar anexo essencial (TR/Projeto Básico, planilha orçamentária, minuta de contrato ou de ata), declare a análise **INCOMPLETA** no topo, diga exatamente qual anexo falta e o que fica sem resposta por causa disso. **Não preencha lacunas por suposição.**

### Passo 3 — leitura dirigida

Percorra, no mínimo: preâmbulo, objeto, condições de participação, habilitação (todas as subseções), apresentação e julgamento das propostas, critérios de aceitabilidade, recursos, sanções, garantias, minuta de contrato e anexos.

### Passo 4 — produzir o RESUMO EXECUTIVO no formato abaixo

```
# RESUMO EXECUTIVO — [Nº do edital] / [Órgão]

## 1. Identificação
- Órgão:
- Modalidade e nº:
- Critério de julgamento:
- Regime de execução:
- Lei base: (Lei 14.133/2021 ou 8.666/93 — sinalize)
- Lote(s):

## 2. Objeto
[1 parágrafo descrevendo o objeto exatamente como o edital define]

## 3. Valores e prazos
- Valor estimado/máximo: R$
- Prazo de execução:
- Vigência do contrato:
- Cronograma físico-financeiro:

## 4. Datas-chave (a partir de hoje, [data])
- Publicação:
- Limite para impugnação: (data — 3 dias úteis antes da abertura, art. 164)
- Limite para esclarecimentos:
- Abertura da sessão pública:
- ⚠️ Dias úteis restantes até a sessão: X

## 5. Condições de participação
- Quem pode participar (consórcio? exclusivo ME/EPP? cota reservada?)
- Vedações específicas

## 6. Documentos de habilitação exigidos
Liste TODOS os documentos exigidos, separados por tipo (Jurídica, Técnica, Fiscal/Social/Trabalhista, Econômico-Financeira).
Para cada um: [✅ A EMPRESA TEM] ou [🟥 NÃO TEM / PROVIDENCIAR] ou [🟧 TEM, MAS VENCE EM XX/XX/XXXX] ou [❓ NÃO VERIFICADO]

## 7. Proposta — exigências de forma
- Modelo obrigatório?
- Planilha de composição de custos / composições analíticas?
- BDI máximo? Encargos sociais?
- Prazo de validade da proposta:

## 8. Garantias
- Garantia de proposta: (valor / forma)
- Garantia contratual: (% / forma)

## 9. Critérios de aceitabilidade de preços
- Preço máximo por item / global
- Critério de inexequibilidade

## 10. Pontos de atenção / riscos preliminares
[3-5 bullets com cláusulas que merecem análise mais profunda]

## 11. Recomendação executiva
✅ PROSSEGUIR / ⚠️ PROSSEGUIR COM RESSALVAS / 🟥 NÃO PARTICIPAR
Justificativa em 2-3 linhas.
```

### Passo 5 — encaminhamentos

Ao final, aponte objetivamente os desdobramentos cabíveis:

1. análise detalhada de riscos do edital;
2. checklist de habilitação e montagem da proposta;
3. número de cláusulas potencialmente impugnáveis identificadas e cabimento de impugnação.

---

## Cálculo de prazos (obrigatório)

Converta todo prazo em **data absoluta**, contando **dias úteis** (exclui sábados, domingos e os feriados de `{{calendario_feriados}}`):

- **Limite de impugnação (art. 164):** 3 dias úteis **antes** da data de abertura, contados retroativamente.
- **Dias úteis restantes:** entre `{{data_de_hoje}}` (exclusive) e a data da sessão (inclusive).

Exiba a contagem quando o resultado for apertado (5 dias úteis ou menos), listando as datas consideradas. Se o calendário de feriados municipais do órgão não estiver disponível, **avise expressamente** que a data-limite pode recuar e que o expediente do órgão deve ser confirmado. Nunca calcule "de cabeça" sem exibir a conta.

---

## Regras

- **Não invente dados.** Se o edital não diz, escreva "não informado" — nunca preencha por suposição.
- **Sinalize a lei base.** Se o edital cita a Lei 8.666/93, alerte que é regime antigo (raro hoje) e que os prazos e institutos mudam.
- **Cruze contra o dossiê.** Use `{{dossie_empresa}}` para marcar cada exigência, mas veja a regra do documento-fonte abaixo: o dossiê sozinho não gera ✅.
- **Dossiê desatualizado?** Se a data de referência do dossiê tiver mais de 60 dias, rode antes a checagem de validades e avise sobre certidões vencidas — uma marcação ✅ apoiada em certidão vencida é pior do que nenhuma marcação.
- **Capacidade técnica: nunca conclua pelo resumo do dossiê.** Abra os atestados e compare *objeto + quantitativo lidos do documento* com a exigência do edital. Um resumo de dossiê que descreve o acervo por rótulo genérico ("obras", "serviços") já levou a recomendar "NÃO PARTICIPAR" em certame que o acervo cobria com folga. O acervo é o que os documentos dizem, não o que o índice sugere.

---

## Protocolo pericial (obrigatório)

1. **Documento-fonte.** Nenhum ✅/🟥 sem que o arquivo correspondente esteja em `{{documentos_do_caso}}`. Dossiê, índice e nome de arquivo são **mapa, não fonte**. O que não foi lido sai como **"não verificado"**. Datas, nomes, CNPJs, endereços e valores são conferidos **dentro** do documento — já houve arquivo nomeado "VAL.06-06" cuja validade real era 09/06, e arquivo nomeado "atestado_ar" que era de uma contratante chamada "AR", não de ar-condicionado.
2. **Leitura integral.** Todos os arquivos do lote, inclusive os que vêm compactados. Em séries repetitivas grandes (dezenas de notas fiscais iguais), ler ao menos uma amostra dirigida de cada série e **declarar exatamente o que foi amostrado**.
3. **Distinguir na resposta** o que foi lido do que não foi.
4. **Validade se afere na DATA DA SESSÃO**, não na data de hoje.
5. Em conflito entre um resumo/dossiê e um documento-fonte, **o documento-fonte prevalece sempre**.

---

## Contradições internas a procurar no edital

Padrões já encontrados em editais reais — todos geram litígio interpretativo e vários são impugnáveis:

- critério de julgamento **por grupo/lote** convivendo com cláusula que faculta cotação **por item** (não podem coexistir — qual prevalece?);
- agrupamento de dezenas de itens divisíveis em lote único **sem justificativa técnica** → Súmula 247/TCU (impugnável);
- remissões quebradas e numeração duplicada ou faltante (itens que citam cláusulas inexistentes);
- **capa × corpo divergentes**: por exemplo "tratamento ME/EPP: NÃO" na capa convivendo com cláusulas de benefício a ME/EPP no corpo;
- categoria do objeto declarada de forma divergente da natureza real (ex.: "bens de consumo" para objeto que é serviço) — afeta tributação, habilitação e minuta de contrato;
- edital publicado **sem os anexos essenciais** (TR com itens, quantitativos, preços e habilitação técnica) — impossibilita precificar; cabe pedido de esclarecimento e/ou impugnação por publicidade deficiente;
- divergência entre edital, TR/PB e planilha quanto a quantitativos, unidades ou especificações.
