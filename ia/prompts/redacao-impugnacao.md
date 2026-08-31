# Redação de Impugnação ao Edital

Este prompt produz a minuta de **impugnação ao edital** — ataque administrativo a cláusulas do instrumento convocatório **antes** da sessão pública, com fundamento no art. 164 da Lei 14.133/2021. Entrega a peça completa (endereçamento, tempestividade, fatos, direito e pedido com redação alternativa concreta), o cálculo da data-limite em dias úteis e o relatório de verificação das citações jurisprudenciais.

## Entradas

- `{{edital_texto}}` — edital e anexos, com as cláusulas atacadas identificadas por item e página.
- `{{ficha_edital}}` — modalidade e número, processo administrativo, órgão/entidade, objeto, **data e hora da abertura da sessão**, forma de protocolo exigida (plataforma eletrônica, e-mail, protocolo físico).
- `{{clausulas_atacadas}}` — relação das cláusulas a impugnar, com o vício apontado e o fundamento mapeado (tipicamente vindo do relatório de riscos).
- `{{dados_do_impugnante}}` — razão social, CNPJ, endereço **atual**, nome completo, CPF e qualificação do representante legal com poderes comprovados.
- `{{dossie_empresa}}` — dossiê da empresa cliente (para o teste de espelho e para demonstrar o prejuízo concreto à competitividade).
- `{{data_de_hoje}}`
- `{{calendario_feriados}}` — feriados nacionais, estaduais e municipais aplicáveis ao órgão.
- `{{base_juridica}}` — Lei 14.133/2021 (art. 164 em especial), jurisprudência consolidada e glossário. O fundamento jurisprudencial é o coração da impugnação: as súmulas do TCU (222, 247, 257, 263, 273) e as teses consolidadas pertinentes ao vício atacado sustentam a peça.

---

## Pré-requisitos

### 1. Verificar o prazo

- **Prazo:** até **3 dias úteis** antes da data de abertura da sessão (art. 164).
- Calcule a data-limite retroativamente a partir da data da sessão, excluindo sábados, domingos e os feriados de `{{calendario_feriados}}`. **Exiba a contagem**, listando as datas consideradas.
- Se os feriados municipais do órgão não forem conhecidos, avise que a data-limite pode recuar e que o expediente do órgão deve ser confirmado.
- 🛑 **Se o prazo já passou: não redija a impugnação.** Informe que os caminhos remanescentes são o pedido de esclarecimento, a representação ao órgão de controle externo ou a via judicial (mandado de segurança), e que essas alternativas pedem consultoria jurídica especializada.

### 2. Identificar com precisão a cláusula atacada

Para cada cláusula: qual item do edital, o que diz literalmente, por que é ilegal ou abusiva, qual dispositivo legal e qual tese jurisprudencial a sustentam, e **qual redação alternativa se propõe**.

---

## Estrutura da peça

```
ILUSTRÍSSIMO(A) SENHOR(A) [PREGOEIRO(A) / AGENTE DE CONTRATAÇÃO / PRESIDENTE DA COMISSÃO DE CONTRATAÇÃO]
DO(A) [ÓRGÃO / SECRETARIA / ENTIDADE]

Ref.: [Modalidade] nº [XX/AAAA] — Processo Administrativo nº [XXXX]
Objeto: [transcrever o objeto do edital]

[RAZÃO SOCIAL DA EMPRESA], pessoa jurídica de direito privado, inscrita no CNPJ sob o nº [XX.XXX.XXX/XXXX-XX], com sede em [endereço completo], neste ato representada por [qualificação do representante legal], inscrito(a) no CPF sob o nº [XXX.XXX.XXX-XX], vem, com fundamento no art. 164 da Lei nº 14.133/2021, tempestivamente, apresentar

IMPUGNAÇÃO AO EDITAL

pelos fatos e fundamentos jurídicos a seguir expostos.

I — DA TEMPESTIVIDADE

A sessão pública está marcada para [data], razão pela qual o prazo para impugnação se encerra em [data-limite]. Apresentada nesta data, a presente impugnação é TEMPESTIVA.

II — DOS FATOS

[Resumir o ponto controverso: o que o edital exige, em qual cláusula ou item, e por que a exigência compromete a competitividade do certame ou impede indevidamente a participação da Impugnante.]

III — DO DIREITO

[Argumentação jurídica estruturada, um tópico por vício:
- dispositivo da Lei 14.133/2021 violado, com o artigo;
- princípio violado (competitividade, isonomia, vinculação ao instrumento convocatório, proporcionalidade, julgamento objetivo);
- jurisprudência em sentido análogo — sem inventar número de acórdão; não havendo certeza, usar formulação genérica ("este Tribunal de Contas tem reiteradamente decidido...");
- doutrina, se pertinente.]

IV — DO PEDIDO

Ante o exposto, requer:

a) o RECEBIMENTO da presente impugnação, por tempestiva;
b) o ACOLHIMENTO da impugnação, com a consequente ALTERAÇÃO da(s) cláusula(s) [identificar item] para [propor a redação alternativa] OU a sua EXCLUSÃO;
c) subsidiariamente, [pedido subsidiário, se cabível];
d) a REPUBLICAÇÃO do edital com a devida reabertura do prazo legal, nos termos do art. 55, §1º, da Lei nº 14.133/2021.

Nestes termos, pede deferimento.

[Cidade], [data por extenso].

_______________________________
[NOME DO REPRESENTANTE LEGAL]
CPF [XXX.XXX.XXX-XX]
Representante legal — [RAZÃO SOCIAL DA EMPRESA]
```

---

## Conteúdo do tópico "DO DIREITO" — roteiro por tipo de vício

### Direcionamento / restrição à competitividade
- Princípios da isonomia e da competitividade (art. 5º)
- Vedação a exigências desnecessárias ou desproporcionais (art. 67, §3º)
- Tese consolidada sobre atestados, com formulação cautelosa

### Atestado com quantitativos excessivos
- Art. 67, §2º — vedação a exigir quantitativos superiores a 50% do objeto
- Súmula 263/TCU e a regra do **somatório de atestados** (é vedado exigir que o quantitativo conste de um único atestado)

### Capital social ou patrimônio líquido acima do limite
- Art. 69, §1º — teto de 10% do valor estimado
- Vedação à exigência cumulativa de PL **e** capital social
- Índices contábeis: exigir acima de 1,0 demanda justificativa técnica; índice sem fórmula no edital ofende o julgamento objetivo

### Visita técnica obrigatória
- Art. 63 — a obrigatoriedade é excepcional e exige justificativa; admite-se a substituição por declaração de pleno conhecimento das condições locais
- Data única, agendamento restrito ou exigência de representante específico são vícios reconhecidos

### Marca ou modelo específicos
- Art. 41 — vedação à indicação de marca, salvo padronização justificada, e mesmo assim com admissão efetiva de similar de qualidade igual ou superior

### Prazo de publicação insuficiente
- Art. 55 — prazos mínimos por modalidade e por objeto

### Agrupamento indevido de itens divisíveis
- Súmula 247/TCU — adjudicação por item para objeto divisível, salvo prejuízo ao conjunto ou perda de economia de escala, sempre demonstrados no processo

### Garantia em modalidade única
- Art. 96 — a escolha da modalidade (caução, seguro-garantia, fiança bancária, títulos) é do licitante
- Art. 58 — garantia de proposta limitada a 1% do valor estimado

### Vícios internos do edital
- Contradição entre julgamento por grupo e cotação por item; remissões a cláusulas inexistentes; divergência entre capa e corpo; ausência de anexos essenciais (publicidade deficiente, impossibilidade de precificar) — cabem esclarecimento e impugnação cumulados

---

## Regras de redação

- **Não transcreva o edital inteiro.** Cite apenas as cláusulas atacadas, com item e página.
- **Redação técnico-jurídica, mas acessível.** Frases médias, parágrafos curtos, um argumento por parágrafo.
- **Sempre proponha a redação alternativa concreta.** Não basta dizer que é ilegal: diga como a cláusula deveria estar escrita para se tornar lícita.
- **Registre a forma de protocolo** exigida pelo edital (plataforma, e-mail, protocolo físico) e o prazo, ao final da entrega.
- **Ao final da peça, escreva uma nota separada ao cliente:**
  > ⚠️ Esta minuta é apoio técnico. Recomenda-se revisão por advogado antes do protocolo, especialmente para confirmar a jurisprudência citada e adequar a peça ao caso concreto.

---

## Verificação obrigatória antes de entregar a peça

1. **Prazo calculado e exibido**, nunca estimado de memória. Mostre a data-limite absoluta e as datas consideradas na contagem; alerte sobre feriados municipais não confirmados.
2. **Toda citação de jurisprudência deve ser verificada.** Para cada acórdão, súmula ou decisão citada na minuta, confirme que (a) existe e (b) trata do tema afirmado. Citação confirmada: mantenha e anote a fonte. Não confirmada: substitua por fundamento legal puro (artigo de lei) ou marque na minuta como **[A CONFIRMAR COM ADVOGADO]**. **Nunca entregue número de acórdão não verificado como se fosse certo.** Ao final, informe quantas citações foram verificadas e quantas ficaram pendentes.
3. **Conferência de dados** — razão social, CNPJ, endereço atual, qualificação e poderes do representante legal, número do certame e do processo, órgão. Endereço desatualizado na peça é vício evitável.

---

## Formulação indiciária (obrigatória em toda peça)

- Achado documental contra terceiro é **indício, não prova**: formule como "inconsistência que impõe diligência" (art. 64 da Lei 14.133/2021) e **requeira a verificação** — nunca afirme fraude, crime ou má-fé (risco de responsabilização por calúnia ou difamação para a empresa cliente e seu representante).
- Estruture cada achado assim: o documento X (folha/página) declara A; o documento Y declara B; A e B não podem ser simultaneamente verdadeiros; requer-se diligência (ou a providência cabível).
- **Teste de espelho:** antes de usar um vício contra terceiro, confirme que a empresa cliente não carrega o mesmo (capital divergente, endereço desatualizado, declaração reaproveitada). Se carregar, avise antes do protocolo.
- Todo número citado foi recalculado, com a aritmética exibida, e referenciado ao documento de origem.
- Inclua, quando útil, o **pedido subsidiário de diligência** (art. 64) — ele sobrevive mesmo se o pedido principal for negado.
