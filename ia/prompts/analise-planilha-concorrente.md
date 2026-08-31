# Análise de Planilha e Caderno de Concorrente

Este prompt transforma a proposta de preços de um concorrente (ou a da própria empresa cliente, em autoconferência) numa lista de irregularidades **objetivas, verificáveis e fundamentadas**: recálculo aritmético item a item, conferência de quantitativos contra a planilha-base do órgão, exame do BDI e dos encargos sociais, detecção de jogo de planilha e posicionamento da proposta nos limiares de inexequibilidade. Em modo estendido, faz a **perícia documental completa** do caderno de habilitação do concorrente. A saída é matéria-prima para recurso administrativo.

## Entradas

- `{{planilha_concorrente}}` — planilha orçamentária / proposta de preços do concorrente, em formato tabular (itens, unidades, quantidades, preços unitários, totais, BDI, encargos, cronograma). Se vier em PDF, transcreva a tabela integralmente antes de calcular.
- `{{planilha_base}}` — planilha orçamentária de referência do órgão (anexo do edital), com quantitativos, preços unitários de referência e fonte (SINAPI, SICRO, tabela estadual etc.).
- `{{edital_texto}}` — edital e anexos: regras de aceitabilidade de preços, BDI máximo, casas decimais, modelo obrigatório de planilha, exigência de composições analíticas, regime de execução.
- `{{ficha_edital}}` — número, órgão, objeto, valor estimado/orçado pela Administração.
- `{{documentos_do_caso}}` — no modo estendido, o caderno de habilitação do concorrente (contrato social e alterações, balanços, livro diário/ECD, notas explicativas, atestados, CATs, anotações de responsabilidade técnica, registros em conselho, certidões).
- `{{dossie_empresa}}` — dossiê da empresa cliente, para o teste de espelho (não se ataca vício que a própria empresa carrega).
- `{{base_juridica}}` — Lei 14.133/2021 (arts. 23-24, 56-59, 62-70), jurisprudência sobre propostas, inexequibilidade, erro material e saneamento, e contabilidade aplicada à habilitação.

---

## MODO 1 — Análise da planilha de preços

### Passo 1 — recálculo aritmético (obrigatório, exibindo a conta)

Para **cada linha** da planilha:

- `quantidade × preço unitário = total do item` — aponte toda linha em que o produto não confere com o total declarado, com a diferença em R$;
- some os totais dos itens e compare com o **total global declarado**, exibindo a diferença;
- verifique o número de **casas decimais** dos unitários contra o que o edital determina (unitário com mais casas do que o permitido é vício formal e distorce o arredondamento do global);
- verifique se há itens em branco, com quantidade zero ou com preço simbólico (R$ 0,01) — item "zerado" costuma ser tentativa de embutir custo em outro item.

Todo número que entrar no relatório sai deste recálculo ou do documento. Se um cálculo não pôde ser feito (planilha ilegível, coluna ausente), **diga que não pôde**.

### Passo 2 — verificações de mérito

1. **Quantitativos.** Batem com a planilha-base do órgão? Em **empreitada por preço unitário**, quantitativo divergente é desconformidade com o edital. Em empreitada por preço global, verifique o que o edital admite antes de apontar o vício — o regime de execução importa.
2. **BDI.** Está dentro das faixas de referência (tabela abaixo)? Foi detalhado como o edital exige? Inclui IRPJ e CSLL (vedado)? A alíquota de ISS confere com a do município da execução e com o que o edital fixou? Há BDI reduzido para as parcelas de fornecimento de materiais e equipamentos?
3. **Encargos sociais.** O percentual adotado é compatível com a tabela de referência vigente para o estado, na versão correta (onerada ou desonerada)? O percentual declarado na composição de encargos é o mesmo efetivamente aplicado nas composições unitárias?
4. **Preços unitários × referência.** Itens acima do orçamento-base (sobrepreço unitário, motivo objetivo de desclassificação quando o edital fixa aceitabilidade por item) ou artificialmente baixos nos itens finais do cronograma (jogo de planilha).
5. **Inexequibilidade em obras.** Calcule os dois limiares em R$ e posicione a proposta: presunção relativa de inexequibilidade abaixo de **75% do valor orçado** pela Administração; entre **75% e 85%**, exigível garantia adicional equivalente à diferença entre o valor da proposta e 85% do orçado (art. 59, §§ 4º-5º). A presunção é relativa — o licitante tem direito de demonstrar exequibilidade; antecipe esse contra-argumento.
6. **Forma.** Modelo obrigatório respeitado? Composições analíticas entregues quando exigidas (a falta pode gerar desclassificação por vinculação ao edital)? Prazo de validade da proposta? Assinatura do responsável técnico quando exigida?

### Passo 3 — relatório

Produza:

**(a) Tabela de irregularidades** — cada achado com localização exata (item/linha da planilha e página), o valor declarado, o valor correto recalculado, a diferença e a norma ou cláusula do edital violada.

**(b) Classificação de cada achado** como **erro material sanável** ou **vício insanável**. A tese de saneamento é o contra-argumento que o concorrente usará — antecipe-o item a item.

**(c) Impacto** — separe o que **altera o valor global ou a ordem de classificação** (grave) do que não altera.

**(d) Conclusão** sobre a viabilidade de recurso, com o pedido que cada achado sustenta (desclassificação, diligência do art. 64, refazimento da classificação).

---

## Parâmetros de BDI (referência do Acórdão 2.622/2013-TCU-Plenário)

Valores fora do intervalo **não são automaticamente ilegais** — exigem justificativa; mas são forte argumento em recurso quando combinados com outros indícios (sobrepreço, jogo de planilha, inexequibilidade).

> ⚠️ Antes de citar em peça protocolada, confirme os valores no texto do acórdão e em decisões posteriores que o atualizem. A tabela abaixo é síntese de referência.

| Tipo de obra | 1º quartil | Médio | 3º quartil |
|---|---|---|---|
| Construção de edifícios | 20,34% | 22,12% | 25,00% |
| Construção de rodovias e ferrovias | 19,60% | 20,97% | 24,23% |
| Redes de abastecimento de água, coleta de esgoto e construções correlatas | 20,76% | 24,18% | 26,44% |
| Construção e manutenção de estações e redes de distribuição de energia elétrica | 24,00% | 25,84% | 27,86% |
| Obras portuárias, marítimas e fluviais | 22,80% | 27,48% | 30,95% |
| Fornecimento de materiais e equipamentos (BDI reduzido) | 11,10% | 14,02% | 16,80% |

Objetos que não se encaixam diretamente numa das faixas (pavimentação urbana, instalações prediais, manutenção predial) são discutidos caso a caso — verifique **como o próprio edital e o orçamento-base do órgão classificaram** antes de apontar divergência.

### Fórmula do BDI (padrão TCU)

```
BDI = [ (1+AC+S+R+G) × (1+DF) × (1+L) / (1−I) ] − 1
```

Onde AC = administração central; S = seguros; R = riscos; G = garantias; DF = despesas financeiras; L = lucro; I = tributos incidentes sobre o faturamento (PIS, COFINS, ISS; contribuição previdenciária sobre a receita bruta quando desonerado).

### Pontos de ataque frequentes no BDI

- **IRPJ e CSLL dentro do BDI** — vedado (Súmula 254/TCU). Se o detalhamento do concorrente os inclui, é irregularidade objetiva.
- **ISS com alíquota errada** — compare com a alíquota do município de execução e com o que o edital fixou.
- **BDI diferenciado não aplicado** — havendo fornecimento relevante de materiais ou equipamentos, exige-se BDI reduzido sobre essas parcelas.
- **Detalhamento ausente** — muitos editais exigem composição analítica do BDI; a falta é vício formal (verifique se o edital comina desclassificação).
- **Encargos sociais "inventados"** — percentual fora da tabela de referência distorce toda a planilha.

---

## Engenharia de custos — fundamentos aplicados à análise

Base normativa: Decreto 7.983/2013 (obras com recursos federais), Lei 14.133/2021 arts. 23-24 (valor estimado) e 59 (aceitabilidade), jurisprudência do TCU sobre orçamento de obras.

### 1. Estrutura de um preço de obra

```
PREÇO DE VENDA = CUSTO DIRETO × (1 + BDI)
CUSTO DIRETO   = Σ composições unitárias (insumos + mão de obra com encargos + equipamentos)
```

A planilha típica tem: planilha sintética (itens × quantitativos × unitários), composições analíticas de custo unitário, composição de encargos sociais, detalhamento do BDI e cronograma físico-financeiro. **Edital que exige composições analíticas e licitante que não as entrega: desclassificação por vinculação ao edital.** Verifique sempre o que o edital exigiu entregar.

### 2. Referências oficiais de preço

- **SINAPI** — obras civis em geral; referência obrigatória em contratações com recursos federais (Decreto 7.983/2013). Tabelas mensais por estado, nas versões onerada e desonerada.
- **SICRO** — obras rodoviárias e de pavimentação.
- **Tabelas estaduais e setoriais** (ORSE, SEINFRA e equivalentes) — usáveis quando o item não existe no SINAPI/SICRO; o órgão deve indicar a fonte no orçamento-base.

Em análise de concorrente, compare os unitários relevantes com o orçamento-base do órgão (que já é referenciado). Preço unitário **acima** do teto do orçamento-base, quando o edital fixa aceitabilidade por item, é motivo objetivo de desclassificação ou de ajuste.

### 3. Encargos sociais sobre mão de obra

- **Grupos:** A (obrigações básicas: previdência patronal, FGTS, salário-educação, seguro de acidentes, terceiros), B (repouso remunerado, férias, 13º, feriados, aviso prévio), C (incidências de A sobre B), D (reincidências). Horista fica tipicamente na faixa de 110% a 125% (onerado); mensalista, de 68% a 75%. **Não cite percentual exato de memória:** confira a tabela de encargos vigente para o estado no mês do orçamento.
- **Desoneração da folha:** na folha desonerada, a contribuição previdenciária patronal sai da folha e passa a incidir sobre a receita bruta, **dentro do BDI**. Ataques clássicos: o concorrente usa encargo desonerado nas composições **e** não inclui a contribuição sobre receita bruta no BDI (dupla vantagem indevida); ou mistura tabelas oneradas e desoneradas na mesma planilha.
- Verifique a coerência entre o percentual declarado na composição de encargos e o efetivamente aplicado nas composições unitárias.

### 4. Curva ABC e jogo de planilha

- **Curva ABC:** ordene os itens por valor total decrescente. A faixa A (cerca de 80% do valor, concentrada em poucos itens) é onde a análise deve se concentrar; não gaste esforço na faixa C.
- **Jogo de planilha (desbalanceamento):** sobrepreço nos itens do **início** do cronograma (mobilização, terraplenagem, escavação, serviços preliminares) e subpreço nos itens finais — o licitante antecipa caixa e pode abandonar a obra depois. Detecção: comparação item a item com o orçamento-base; o padrão de +X% nos serviços iniciais e −X% nos finais é o indício. O TCU condena reiteradamente o sobrepreço por desbalanceamento.
- **Quantitativos alterados:** o licitante não pode alterar quantitativo da planilha-base, salvo quando o edital admite proposta por preço global com quantitativos próprios em regime de empreitada global — **verifique o regime antes de apontar o vício**.

### 5. Cronograma físico-financeiro

- Deve ser compatível com a planilha (a soma das parcelas mensais fecha com o total) e com os prazos do edital.
- Ataques: desembolso concentrado no início sem lastro físico (reforça a tese de jogo de planilha); parcelas que não fecham com o total proposto (erro aritmético).

### 6. Checklist-resumo da análise de proposta

1. Recalcular a planilha inteira — aritmética, somas e casas decimais.
2. Conferir quantitativos contra a planilha-base (o regime de execução importa).
3. Curva ABC → concentrar na faixa A → comparar unitários com o orçamento-base (sobrepreço e subpreço por item).
4. Procurar o padrão de desbalanceamento início/fim do cronograma.
5. BDI: faixas de referência, detalhamento, IRPJ/CSLL, ISS, tratamento da desoneração.
6. Encargos sociais: coerência interna e com a tabela de referência vigente.
7. Limiares de inexequibilidade (75% e 85%) calculados em R$.
8. Exigências formais do edital: composições entregues? modelo? assinatura do RT? validade da proposta?

---

## MODO 2 — Perícia documental completa do caderno do concorrente

Quando o material incluir o **caderno de habilitação** do concorrente (e não apenas a planilha), execute a perícia completa. Em caderno grande, organize a leitura em lotes (15 a 20 arquivos por bloco), registrando o que já foi conferido.

Vetores a examinar, nesta ordem:

1. **Capital social × balanço.** Ato societário que declara integralização "neste ato" sem lançamento correspondente no livro diário, e balanço registrando capital menor, configura **capital de fachada** — é o achado mais forte, e a diligência do art. 64 torna-se inescapável. Lembre que o capital que conta é o **integralizado**.
2. **Consistência interna do balanço.** Notas explicativas × balanço × DRE × lucros acumulados; identidade Ativo = Passivo + PL; caixa em espécie dominando o ativo; ativo circulante dominado por "outros créditos" genéricos; PL alto com receita irrisória; índices declarados com fórmula errada — **recalcule sempre** (LG = (AC+RLP)÷(PC+PNC); LC = AC÷PC; SG = Ativo Total÷(PC+PNC); CCL = AC−PC). Verifique também as formalidades: exercício exigível, autenticação por livro diário registrado ou recibo da ECD, termos de abertura e encerramento, assinatura de contador com CRC ativo.
3. **Atestados.** Texto idêntico entre emissores distintos, com os mesmos erros de português; ausência de quantitativos, valores e número de contrato; telefone ou e-mail do próprio interessado (ou do contador) como contato do emissor; competência do emissor para atestar (uma unidade executora local não substitui a Secretaria contratante); forma exigida pelo edital não revestida. Esse conjunto caracteriza o padrão "atestado de balcão": valor probatório baixo e atacável.
4. **Registro no conselho profissional.** Registro da pessoa jurídica vencido ou obtido depois dos serviços atestados; responsável técnico com início de vínculo posterior ao período atestado; RT acumulando responsabilidade por várias empresas; atribuição profissional incompatível com o objeto; ramo de atuação averbado que não cobre o objeto.
5. **Endereços múltiplos.** Junta Comercial × Receita Federal × alvará × cadastro de fornecedores × proposta. Já se encontrou quatro endereços simultâneos num único caderno.
6. **Caderno incompleto.** Confira na certidão específica ou de inteiro teor da Junta se **todas** as alterações contratuais foram apresentadas.
7. **Linha do tempo societária.** Mudança abrupta de ramo de atividade (por exemplo, de comércio varejista para obras de engenharia) pouco antes do certame; aumentos de capital às vésperas da sessão sem lastro contábil.
8. **DRE × acervo.** Receita anual incompatível com o volume de serviços atestados (empresa que atesta ter executado milhões com receita declarada de centenas de milhares) — é um dos cruzamentos mais eficazes em recurso.
9. **Jurisdição e vigência das certidões** na data da sessão, e datas de emissão contra o prazo-limite de entrega.

### Regras do laudo

- **Formulação indiciária, sempre.** Achado documental é indício, não prova: escreva "inconsistência que impõe diligência" (art. 64 da Lei 14.133/2021) e **requeira a verificação** — nunca afirme fraude, crime ou má-fé (risco de responsabilização por calúnia ou difamação para a empresa cliente e seu representante).
- **Seção obrigatória "o que é legítimo e verificável".** Análise que só enxerga defeito perde credibilidade e leva o cliente a subestimar o adversário.
- **Teste de espelho.** Antes de atacar um vício, confirme em `{{dossie_empresa}}` que a empresa cliente **não carrega o mesmo vício** (capital divergente, endereço desatualizado, declaração reaproveitada, índices com fórmula errada). Se carregar, avise antes de qualquer protocolo.
- **Cada achado citado com documento e página**, e cada número recalculado com a aritmética exibida.
- **Códigos de autenticação** das certidões e dos documentos listados, para verificação nos portais emissores.

---

## Regras gerais

- **Todo número citado sai do recálculo ou do documento — nunca de estimativa.** Se não deu para recalcular, diga que não deu.
- **Distinga sempre** o erro que altera o valor global ou a classificação daquele que não altera.
- **Antecipe a tese defensiva:** admite-se o saneamento de erros materiais em propostas quando a correção não majora o valor global. Um recurso forte ataca vícios que **não** são saneáveis, ou cuja correção altera o valor ou a ordem de classificação.
- **Antes de citar qualquer acórdão ou súmula no relatório**, confirme número e tese; não sendo possível confirmar, use fundamento legal puro ou marque a citação como **[A CONFIRMAR]**.

---

## Protocolo pericial (obrigatório)

1. **Documento-fonte.** Nenhuma afirmação sem o arquivo aberto e lido nesta análise; o que não foi lido sai como **"não verificado"**.
2. **Leitura integral.** Todos os arquivos, inclusive compactados; em séries repetitivas grandes, amostra dirigida declarada.
3. **Todo número recalculado** e referenciado ao documento e à página de origem.
4. Em conflito entre resumo e documento-fonte, **o documento-fonte prevalece**.
