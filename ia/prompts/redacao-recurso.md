# Redação de Recurso Administrativo

Este prompt produz a minuta de **recurso administrativo** contra ato decisório proferido no curso da licitação — habilitação ou inabilitação, julgamento de propostas, desclassificação, anulação ou revogação —, com fundamento no art. 165 da Lei 14.133/2021. Entrega a peça completa (endereçamento duplo, tempestividade e pressupostos, fatos, direito e pedido), o cálculo da data-limite em dias úteis e o relatório de verificação das citações jurisprudenciais.

## Entradas

- `{{ato_recorrido}}` — descrição do ato: qual decisão, proferida por quem, com que fundamento, e **data da intimação ou da publicação**.
- `{{ficha_edital}}` — modalidade e número, processo administrativo, órgão, objeto, autoridade superior competente para o julgamento do recurso, forma de protocolo exigida.
- `{{edital_texto}}` — edital e anexos, em especial as cláusulas invocadas na decisão recorrida e as que sustentam a tese da recorrente.
- `{{documentos_do_caso}}` — ata da sessão (para verificar o registro da intenção motivada de recorrer), documentos apresentados pela empresa cliente, e, quando o recurso for contra ato favorável a concorrente, o caderno ou a proposta do concorrente e as consultas públicas que instruem a prova.
- `{{dados_do_recorrente}}` — razão social, CNPJ, endereço **atual**, nome completo, CPF e qualificação do representante legal.
- `{{dossie_empresa}}` — dossiê da empresa cliente (prova documental e teste de espelho).
- `{{data_de_hoje}}`
- `{{calendario_feriados}}`
- `{{base_juridica}}` — Lei 14.133/2021 (art. 165 em especial), jurisprudência consolidada — em recursos sobre habilitação, as teses de **saneamento de falhas / formalismo moderado** e as de **atestados** são as mais frequentes — e glossário.

---

## Pré-requisitos

### 1. Confirmar o ato recorrido

- Qual é o ato: inabilitação da empresa cliente / habilitação indevida de concorrente / desclassificação de proposta / classificação indevida de proposta de concorrente / anulação ou revogação?
- Qual a data da intimação ou publicação do ato?
- **Houve manifestação de intenção de recorrer na sessão?** No pregão, a intenção motivada registrada em ata é **pré-requisito de admissibilidade**; a omissão acarreta preclusão. Verifique na ata antes de redigir e, se não houver registro, avise expressamente que o recurso pode não ser conhecido.

### 2. Verificar o prazo

- **Prazo:** 3 dias úteis, em regra (art. 165, §3º), contados da intimação.
- Calcule a data-limite somando 3 dias úteis à data da intimação (excluído o dia inicial), desconsiderando sábados, domingos e os feriados de `{{calendario_feriados}}`. **Exiba a contagem.** Alerte se os feriados municipais do órgão não forem conhecidos.
- 🛑 **Se o prazo escoou**, o recurso administrativo está precluso. Informe que resta avaliar a via judicial (mandado de segurança, prazo de 120 dias, com liminar dependente de urgência) e encaminhe a advogado.

### 3. Efeito suspensivo

- Recurso contra o julgamento das propostas e contra o ato de habilitação/inabilitação tem **efeito suspensivo automático**.
- Nos demais casos, o efeito depende de decisão da autoridade — peça-o expressamente e justifique.

---

## Estrutura da peça

```
ILUSTRÍSSIMO(A) SENHOR(A) [AGENTE DE CONTRATAÇÃO / PREGOEIRO(A) / PRESIDENTE DA COMISSÃO],
PARA POSTERIOR APRECIAÇÃO PELA AUTORIDADE SUPERIOR [identificar o cargo]
DO(A) [ÓRGÃO]

Ref.: [Modalidade] nº [XX/AAAA] — Processo Administrativo nº [XXXX]
Recorrente: [RAZÃO SOCIAL DA EMPRESA] — CNPJ [XX.XXX.XXX/XXXX-XX]
Ato recorrido: [descrição] — Intimação em [data]

[RAZÃO SOCIAL DA EMPRESA], qualificada nos autos, neste ato representada por [qualificação do representante legal], vem, com fundamento no art. 165 da Lei nº 14.133/2021, tempestivamente, interpor

RECURSO ADMINISTRATIVO

contra a decisão que [descrição do ato recorrido], pelos fatos e fundamentos a seguir expostos.

I — DA TEMPESTIVIDADE E DOS PRESSUPOSTOS RECURSAIS

A intimação ocorreu em [data], iniciando-se o prazo recursal de 3 (três) dias úteis. Apresentado em [data], o presente recurso é TEMPESTIVO.

A Recorrente manifestou, na sessão, a intenção motivada de recorrer, nos termos exigidos para a modalidade [pregão / concorrência], conforme registrado em ata [indicar a folha/trecho]. Atendidos, portanto, os pressupostos de admissibilidade.

II — DOS FATOS

[Narrativa cronológica e objetiva: o que ocorreu na sessão, qual a decisão do agente de contratação, qual o fundamento invocado e em que ponto a Recorrente diverge. Sem juridiquês nesta seção.]

III — DO DIREITO

[Argumentação jurídica:
- dispositivo legal aplicável;
- princípio do julgamento objetivo (art. 5º), quando o ato decisório se desvia do edital;
- princípio da vinculação ao instrumento convocatório — a Administração não pode exigir além nem aquém do edital;
- os documentos apresentados que demonstram o atendimento da exigência, com referência a folha/página;
- jurisprudência análoga, citada com cautela;
- em recurso contra habilitação de concorrente: demonstração objetiva, documento a documento, de que a exigência do edital não foi atendida, instruída com a prova disponível.]

IV — DO PEDIDO

Ante o exposto, requer:

a) o RECEBIMENTO do recurso, com efeito suspensivo, nos termos do art. 165, §1º, da Lei nº 14.133/2021;
b) a RECONSIDERAÇÃO da decisão recorrida pelo(a) Agente de Contratação;
c) caso mantida, o ENCAMINHAMENTO dos autos à autoridade superior, com o PROVIMENTO do recurso e [pedido principal: declaração de habilitação da Recorrente / inabilitação da licitante [X] / desclassificação da proposta [X] / retorno da fase de julgamento];
d) subsidiariamente, a realização de DILIGÊNCIA, nos termos do art. 64 da Lei nº 14.133/2021, para esclarecimento das inconsistências apontadas;
e) a INTIMAÇÃO dos demais licitantes para, querendo, apresentarem contrarrazões no prazo legal.

Nestes termos, pede deferimento.

[Cidade], [data por extenso].

_______________________________
[NOME DO REPRESENTANTE LEGAL]
CPF [XXX.XXX.XXX-XX]
Representante legal — [RAZÃO SOCIAL DA EMPRESA]
```

---

## Conteúdo do "DO DIREITO" — roteiros por tipo de recurso

### Contra INABILITAÇÃO da empresa cliente
- Demonstrar que o documento exigido **foi** apresentado, com referência exata a folha/arquivo/página
- Havendo erro material, demonstrar que era sanável — formalismo moderado e dever de saneamento (art. 12, III; art. 64)
- Se a exigência em si era ilegal, combinar com argumentação de tipo impugnatório (exigência sem amparo legal não pode fundamentar inabilitação)

### Contra HABILITAÇÃO INDEVIDA de concorrente
- Identificar exatamente qual exigência do edital não foi atendida, cláusula por cláusula
- Instruir com prova: consultas públicas a cadastros e portais, certidões acessíveis, ata da sessão, os próprios documentos do concorrente
- Vetores recorrentes: atestado sem os elementos mínimos ou sem a forma exigida; CAT ausente; RT com atribuição incompatível ou vínculo posterior ao período atestado; capital social divergente entre ato societário e balanço; balanço sem autenticação; índices calculados com fórmula errada; certidão de jurisdição incorreta; endereços divergentes entre documentos
- Fundamentos: arts. 62 a 70

### Contra DESCLASSIFICAÇÃO da proposta da empresa cliente
- Demonstrar que a proposta atende ao edital, ponto a ponto
- Se a desclassificação foi por inexequibilidade: art. 59 — a presunção é **relativa** e assegura o direito de demonstrar a exequibilidade; apresentar a memória de cálculo

### Contra CLASSIFICAÇÃO de proposta de concorrente
- Apontar a inconsistência entre a proposta e o edital, com o recálculo exibido
- Inexequibilidade do concorrente: art. 59, §4º, com os limiares de 75% e 85% calculados em R$
- Sobrepreço unitário acima do orçamento-base quando o edital fixa aceitabilidade por item; desbalanceamento (jogo de planilha); BDI com IRPJ/CSLL embutidos; encargos incompatíveis com a tabela de referência

### Contra ANULAÇÃO ou REVOGAÇÃO
- Princípios da boa-fé, da segurança jurídica e da motivação
- Verificar se houve contraditório prévio; revogação exige motivação de conveniência e oportunidade e respeita direitos adquiridos; anulação exige vício de legalidade demonstrado

---

## Regras de redação

- **A intenção motivada de recorrer registrada em ata é decisiva no pregão.** Confirme antes de redigir; sem ela, o recurso pode não ser conhecido — e isso precisa ser dito ao cliente.
- **Anexe prova.** Recurso sem documento que demonstre o fato dificilmente é provido. Liste os anexos ao final da peça.
- **Comece pelos fatos.** Deixe a argumentação jurídica para o tópico III.
- **Escreva para dois leitores.** O agente de contratação pode reconsiderar; mantida a decisão, quem julga é a autoridade superior. A peça precisa funcionar para ambos.
- **Ao final, escreva nota separada ao cliente:**
  > ⚠️ Recursos têm prazo fatal e impactam diretamente a posição da empresa no certame. Recomenda-se revisão por advogado antes do protocolo, especialmente para confirmar as citações jurisprudenciais.

---

## Verificação obrigatória antes de entregar a peça

1. **Prazo calculado e exibido**, nunca estimado de memória (3 dias úteis a partir da intimação, art. 165, §3º). Mostre a data-limite absoluta e as datas consideradas; alerte sobre feriados municipais não confirmados.
2. **Toda citação de jurisprudência deve ser verificada.** Para cada acórdão, súmula ou decisão citada, confirme que (a) existe e (b) trata do tema afirmado. Citação confirmada: mantenha e anote a fonte. Não confirmada: substitua por fundamento legal puro ou marque como **[A CONFIRMAR COM ADVOGADO]**. **Nunca entregue número de acórdão não verificado como se fosse certo.** Informe ao final quantas citações foram verificadas.
3. **Conferência de dados** — razão social, CNPJ, endereço atual, qualificação e poderes do representante legal, número do certame e do processo, órgão, data da intimação.

---

## Formulação indiciária (obrigatória em toda peça)

- Achado documental contra terceiro é **indício, não prova**: formule como "inconsistência que impõe diligência" (art. 64 da Lei 14.133/2021) e **requeira a verificação** — nunca afirme fraude, crime ou má-fé (risco de responsabilização por calúnia ou difamação para a empresa cliente e seu representante).
- Estruture cada achado assim: o documento X (folha/página) declara A; o documento Y declara B; A e B não podem ser simultaneamente verdadeiros; requer-se diligência ou a inabilitação, conforme o caso.
- **Teste de espelho:** antes de usar um vício do concorrente, confirme que a empresa cliente não carrega o mesmo (capital divergente, endereço desatualizado, declaração reaproveitada, índices com fórmula errada). Se carregar, avise antes do protocolo.
- Todo número citado foi recalculado, com a aritmética exibida, e referenciado ao documento de origem.
- Inclua o **pedido subsidiário de diligência** (art. 64) — ele sobrevive mesmo se o pedido principal for negado.
