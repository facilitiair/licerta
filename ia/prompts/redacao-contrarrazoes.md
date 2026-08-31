# Redação de Contrarrazões a Recurso Administrativo

Este prompt produz a minuta de **contrarrazões** — a defesa da empresa cliente contra recurso interposto por outro licitante em face de ato que lhe foi favorável (habilitação, classificação, adjudicação). Entrega a peça completa (tempestividade, síntese fiel do recurso, refutação ponto a ponto, inexistência de vício na decisão recorrida e pedido), o cálculo da data-limite em dias úteis e o relatório de verificação das citações jurisprudenciais.

## Entradas

- `{{recurso_do_concorrente}}` — **inteiro teor** do recurso a ser rebatido. Sem ele não há contrarrazões: se estiver ausente, interrompa e peça.
- `{{ficha_edital}}` — modalidade e número, processo administrativo, órgão, objeto, autoridade superior competente, forma de protocolo exigida.
- `{{edital_texto}}` — edital e anexos, especialmente as cláusulas que sustentam o ato recorrido.
- `{{ato_favoravel}}` — descrição do ato impugnado pelo concorrente (habilitação, classificação, adjudicação) e a **data da intimação para contrarrazões**.
- `{{documentos_do_caso}}` — documentos da empresa cliente que provam o atendimento às exigências (certidões, atestados, CATs, balanço, planilha, declarações), com folha/página; ata da sessão.
- `{{dados_do_recorrido}}` — razão social, CNPJ, endereço **atual**, nome completo, CPF e qualificação do representante legal.
- `{{dossie_empresa}}` — dossiê da empresa cliente, incluindo histórico de contratos executados e preços praticados (útil na defesa de exequibilidade).
- `{{data_de_hoje}}`
- `{{calendario_feriados}}`
- `{{base_juridica}}` — Lei 14.133/2021, jurisprudência consolidada — com atenção às teses sobre **recursos**, **princípios** (vinculação ao edital, julgamento objetivo) e **formalismo moderado / saneamento**, esta última decisiva quando o concorrente alega vício formal sanável — e glossário.

---

## Pré-requisitos

### 1. Confirmar o contexto

- Qual licitante recorreu e contra qual ato?
- A empresa cliente foi intimada para apresentar contrarrazões? Em que data?
- O inteiro teor do recurso está disponível? Sem ele, não redija.

### 2. Verificar o prazo

- **Prazo:** 3 dias úteis a partir da intimação (art. 165, §3º).
- Calcule a data-limite somando 3 dias úteis à data da intimação (excluído o dia inicial), desconsiderando sábados, domingos e os feriados de `{{calendario_feriados}}`. **Exiba a contagem.** Alerte se os feriados municipais do órgão não forem conhecidos.

### 3. Testar a admissibilidade do recurso adversário

Antes do mérito, procure fundamentos de **não conhecimento**: intempestividade, ausência de manifestação motivada de intenção de recorrer na sessão (no pregão), ilegitimidade, falta de interesse recursal, ausência de razões (recurso genérico), pedido juridicamente impossível. Argumento de admissibilidade é mais econômico e mais elegante que o de mérito — quando existir, vai como pedido principal.

---

## Estrutura da peça

```
ILUSTRÍSSIMO(A) SENHOR(A) [AGENTE DE CONTRATAÇÃO / PREGOEIRO(A) / PRESIDENTE DA COMISSÃO],
PARA POSTERIOR APRECIAÇÃO PELA AUTORIDADE SUPERIOR DO(A) [ÓRGÃO]

Ref.: [Modalidade] nº [XX/AAAA] — Processo Administrativo nº [XXXX]
Recorrente: [Razão social do concorrente]
Recorrida: [RAZÃO SOCIAL DA EMPRESA] — CNPJ [XX.XXX.XXX/XXXX-XX]

[RAZÃO SOCIAL DA EMPRESA], qualificada nos autos, neste ato representada por [qualificação do representante legal], vem, no prazo legal, com fundamento no art. 165, §3º, da Lei nº 14.133/2021, apresentar

CONTRARRAZÕES

ao recurso interposto pela empresa [recorrente], pelos fundamentos a seguir expostos.

I — DA TEMPESTIVIDADE

A intimação para contrarrazões ocorreu em [data], razão pela qual a presente peça, apresentada nesta data, é TEMPESTIVA.

II — DA SÍNTESE DO RECURSO

A Recorrente alega, em síntese, que [resumir os argumentos do recurso em 1 ou 2 parágrafos, com fidelidade]. Sustenta, em consequência, [pedido do recurso].

III — DA INADMISSIBILIDADE DO RECURSO
[Somente se houver fundamento: intempestividade, ausência de intenção motivada registrada em ata, ilegitimidade, ausência de razões. Demonstrar objetivamente.]

IV — DA IMPROCEDÊNCIA DO RECURSO

[Refutação ponto a ponto, respondendo a CADA alegação, na ordem em que foram deduzidas. Use:
- demonstração factual: a Recorrida atendeu ao edital, com indicação de folha/página do documento;
- cláusulas do edital que sustentam o ato recorrido;
- dispositivos da Lei 14.133/2021 aplicáveis;
- princípios: vinculação ao instrumento convocatório, julgamento objetivo, formalismo moderado;
- quando o recurso for genérico ou desacompanhado de prova: apontar a ausência de demonstração concreta;
- quando houver tentativa de inovar o edital ou de criar exigência não prevista: arts. 5º e 164 — a fase de impugnação está preclusa.]

V — DA INEXISTÊNCIA DE VÍCIO NA DECISÃO RECORRIDA

[Demonstrar que o ato recorrido está em conformidade com o edital e com a lei, e que não há fundamento para reforma.]

VI — DO PEDIDO

Ante o exposto, requer:

a) o RECEBIMENTO destas contrarrazões;
b) o NÃO CONHECIMENTO do recurso, em razão de [fundamento de admissibilidade, se houver];
c) subsidiariamente, o IMPROVIMENTO do recurso, mantendo-se incólume a decisão que [descrição do ato favorável à Recorrida];
d) a CONSEQUENTE adjudicação do objeto à Recorrida, oportunamente.

Nestes termos, pede deferimento.

[Cidade], [data por extenso].

_______________________________
[NOME DO REPRESENTANTE LEGAL]
CPF [XXX.XXX.XXX-XX]
Representante legal — [RAZÃO SOCIAL DA EMPRESA]
```

---

## Roteiros por tipo de alegação a rebater

### O concorrente alega que faltou o documento X
- Mostrar o documento: arquivo, folha, página, data de emissão e validade
- Havendo pequena divergência formal, invocar o formalismo moderado e o dever de saneamento (art. 12, III; art. 64) — erro material sanável não justifica inabilitação

### O concorrente alega que o atestado não cobre o objeto
- Detalhar o atestado: contratante, objeto, quantitativos, período, RT, CAT correspondente
- Demonstrar a equivalência funcional e quantitativa com o exigido, e que o somatório de atestados é admitido
- Lembrar que a exigência de quantitativo não pode ultrapassar 50% do objeto (art. 67, §2º)

### O concorrente alega que a proposta é inexequível
- Apresentar a memória de cálculo e as composições
- Invocar o art. 59: a presunção de inexequibilidade é **relativa** e assegura o direito de demonstrar a exequibilidade
- Trazer precedentes da própria empresa — preços unitários praticados em contratos anteriores de objeto semelhante, com identificação do contrato e do órgão

### O concorrente alega irregularidade fiscal ou trabalhista
- Apresentar as certidões vigentes na data da sessão, com código de autenticação
- Lembrar que a consulta pública on-line a cadastros e portais oficiais é meio de prova
- Certidão positiva com efeito de negativa equivale à negativa para fins de habilitação

### O concorrente alega vício na razão social, no endereço ou nos dados cadastrais
- Juntar a alteração contratual que prova a continuidade da pessoa jurídica
- Demonstrar que a divergência é formal e não induz dúvida sobre a identidade do licitante

### O concorrente faz alegação genérica, sem prova
- Ônus probatório: quem alega, prova
- Requerer o improvimento por ausência de comprovação, sem deixar de responder ao mérito subsidiariamente

---

## Regras de redação

- **Rebata ponto a ponto.** Nenhuma alegação do recurso pode ficar sem resposta — silêncio sobre um tópico é lido como concordância.
- **Não distorça os argumentos do concorrente.** Cite-os com fidelidade; atacar uma versão deturpada enfraquece a defesa e expõe a peça.
- **Quando houver fundamento de admissibilidade, peça o não conhecimento como pedido principal**, deixando o mérito em caráter subsidiário.
- **Prove com documento.** Cada afirmação de fato remete a um documento identificado por folha ou página, com validade e código de autenticação quando houver.
- **Ao final, escreva nota separada ao cliente:**
  > ⚠️ Esta minuta deve ser revisada por advogado antes do protocolo. Contrarrazões mal apresentadas podem custar uma vitória já obtida.

---

## Verificação obrigatória antes de entregar a peça

1. **Prazo calculado e exibido**, nunca estimado de memória (3 dias úteis a partir da intimação). Mostre a data-limite absoluta e as datas consideradas; alerte sobre feriados municipais não confirmados.
2. **Toda citação de jurisprudência deve ser verificada.** Para cada acórdão, súmula ou decisão citada, confirme que (a) existe e (b) trata do tema afirmado. Citação confirmada: mantenha e anote a fonte. Não confirmada: substitua por fundamento legal puro ou marque como **[A CONFIRMAR COM ADVOGADO]**. **Nunca entregue número de acórdão não verificado como se fosse certo.** Informe ao final quantas citações foram verificadas.
3. **Conferência de dados** — razão social, CNPJ, endereço atual, qualificação e poderes do representante legal, número do certame e do processo, órgão, data da intimação.
4. **Conferência da prova citada:** todo documento invocado na defesa precisa ter sido efetivamente lido nesta análise, com validade aferida **na data da sessão**.

---

## Formulação indiciária (obrigatória em toda peça)

- Achado documental contra terceiro é **indício, não prova**: formule como "inconsistência que impõe diligência" (art. 64 da Lei 14.133/2021) e **requeira a verificação** — nunca afirme fraude, crime ou má-fé (risco de responsabilização por calúnia ou difamação para a empresa cliente e seu representante).
- Estruture cada achado assim: o documento X (folha/página) declara A; o documento Y declara B; A e B não podem ser simultaneamente verdadeiros; requer-se diligência ou a providência cabível.
- **Teste de espelho:** se as contrarrazões contra-atacarem apontando vícios do recorrente, confirme antes que a empresa cliente não carrega o mesmo vício.
- Todo número citado foi recalculado, com a aritmética exibida, e referenciado ao documento de origem.
