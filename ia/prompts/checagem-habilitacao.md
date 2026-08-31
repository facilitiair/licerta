# Checagem de Habilitação (empresa cliente × edital)

Este prompt cruza, uma a uma, as exigências de habilitação de um edital com a documentação real da empresa cliente e devolve uma **Checklist de Habilitação** com status por item (tem / vence antes da sessão / não tem / não verificado), o recálculo dos índices contábeis exigidos, os cruzamentos periciais obrigatórios (capital, endereço, atestados, jurisdição das certidões) e um parecer final sobre a habilitabilidade da empresa naquele certame.

## Entradas

- `{{edital_texto}}` — edital completo, com ênfase na seção de habilitação e nos anexos que a detalham.
- `{{ficha_edital}}` — número, órgão, objeto, valor estimado e **data da sessão pública** (sem ela não há conferência de validade).
- `{{dossie_empresa}}` — dossiê da empresa cliente: identificação societária e razões sociais anteriores, sede e filiais, capital social integralizado, CNAEs, responsáveis técnicos e registros em conselho, acervo técnico (atestados/CATs com objeto, quantitativos, valor, contratante, período, RT e nº da CAT), certidões com validades, balanços e índices, cadastros, declarações padrão, seguros e garantias.
- `{{documentos_do_caso}}` — conteúdo dos documentos efetivamente abertos e lidos nesta análise. O que não estiver aqui não pode receber ✅.
- `{{data_de_hoje}}`
- `{{calendario_feriados}}` — feriados nacionais, estaduais e municipais aplicáveis.
- `{{base_juridica}}` — Lei 14.133/2021 (arts. 62 a 70), jurisprudência consolidada sobre habilitação técnica, jurídica, fiscal e econômica, contabilidade aplicada à habilitação e glossário.

---

## Procedimento

### Passo 1 — mapear TODAS as exigências

Agrupe as exigências do edital em:

1. Habilitação Jurídica (art. 66)
2. Habilitação Técnica (art. 67)
3. Habilitação Fiscal, Social e Trabalhista (art. 68)
4. Habilitação Econômico-Financeira (art. 69)
5. Declarações específicas exigidas
6. Documentos do responsável técnico (registro em conselho, anotação de responsabilidade técnica, comprovação de vínculo)

Transcreva a exigência como o edital a redige — inclusive a **forma** exigida (assinatura digital, firma reconhecida, nota fiscal anexa, prazo máximo de emissão). Forma exigida para um documento é cláusula, não suposição.

### Passo 2 — atribuir o status de cada exigência

| Status | Significado |
|---|---|
| ✅ TEMOS | Documento lido nesta análise, vigente **na data da sessão** e compatível com a exigência |
| 🟧 TEMOS, MAS VENCE | Documento existe, mas a validade expira **antes da sessão** — precisa renovar |
| 🟥 NÃO TEMOS | A empresa não possui o documento — precisa providenciar do zero |
| ❓ NÃO VERIFICADO | O arquivo não foi aberto nesta análise, ou o dossiê não permite concluir |

Nunca há ✅ por dedução, analogia ou nome de arquivo.

### Passo 3 — entregar a CHECKLIST DE HABILITAÇÃO

```
# CHECKLIST DE HABILITAÇÃO — [Nº do edital] / [Órgão]
Sessão pública: [data] | Hoje: [data] | Dias úteis restantes: [X]

## 1. Habilitação Jurídica
- [ ] ✅ Contrato social consolidado e alterações — lido, doc [ref]
- [ ] 🟧 Certidão simplificada da Junta Comercial — emissão [data]; o edital exige emissão nos últimos 90 dias → reemitir até [data]
- ...

## 2. Habilitação Técnica
- [ ] ✅ Registro da empresa no conselho profissional — validade [data] (posterior à sessão: OK)
- [ ] 🟥 Atestado de execução de [objeto] com quantitativo mínimo de [X] — o acervo cobre [Y] no atestado [ref] e [Z] no atestado [ref]; somatório = [Y+Z]. **Insuficiente / Suficiente.**
- [ ] ❓ CAT correspondente ao atestado [ref] — não consta no material lido
- ...

## 3. Habilitação Fiscal, Social e Trabalhista
- [ ] ✅ Certidão [órgão] — válida até [data]
- ...

## 4. Habilitação Econômico-Financeira
- [ ] ✅ Balanço patrimonial do exercício [ano] — autenticado (livro diário registrado / recibo de entrega da ECD)
- [ ] Índices exigidos: LG ≥ [x], LC ≥ [x], SG ≥ [x] — **recalculados** (ver seção de análise contábil): LG = [valor], LC = [valor], SG = [valor] → ATENDE / NÃO ATENDE
- [ ] [se exigido] Capital social ou PL mínimo de R$ [X] — comparar com o capital **integralizado** e com o PL do balanço

## 5. Declarações
- [ ] ✅ Declarações exigidas — cada uma deve citar o nº do certame e o órgão CORRETOS dentro do texto
- ...

## 6. Documentos do responsável técnico
- [ ] ✅ Registro do RT no conselho — validade [data]
- [ ] ✅ Comprovação de vínculo (contrato social, CLT ou contrato de prestação de serviços — art. 67, §1º)
- [ ] ❓ Anotação de responsabilidade técnica específica para este objeto — emitir se exigida

---

## RESUMO
- Documentos OK: X
- Documentos a renovar antes da sessão: Y
- Documentos faltantes (a providenciar): Z
- Itens não verificados: W
- ⚠️ Lacunas críticas (que inviabilizam a participação): V

## PARECER FINAL
✅ HABILITÁVEL / ⚠️ HABILITÁVEL COM AÇÕES URGENTES / 🟥 NÃO HABILITÁVEL
Justificativa em 2-3 linhas.
```

---

## Regras

- **Nunca afirme que um documento "vence depois da sessão" sem confirmar a data da sessão** no edital.
- **Atestados técnicos:** compare cuidadosamente OBJETO + QUANTITATIVO + FORMA. Não basta ter "algum" atestado — tem que ser compatível, e revestir a forma que o edital exige. O somatório de atestados é admitido; exigência de quantitativo superior a 50% do objeto é atacável (art. 67, §2º; Súmula 263/TCU).
- **Liste o que falta antes de dar parecer.** O cliente precisa enxergar as lacunas, não só a conclusão.
- **Dúvida de interpretação da exigência:** sinalize com ❓ e recomende consulta a advogado.
- **Certidão vencida nunca é ✅.** Marque 🟥 com a observação "vencida em DD/MM/AAAA — renovar antes da sessão".
- **Certidão emitida depois do prazo-limite de entrega não existe para o certame.** Confira as datas de **emissão** de todas as certidões contra o prazo-limite fixado no edital, além das validades.

---

## Cálculo de validades (obrigatório)

Toda validade se afere na **data da sessão**, não em `{{data_de_hoje}}`. Monte a conferência como tabela paramétrica ("vigente se a sessão ocorrer até [data]") e destaque o que vence **entre hoje e a sessão** — é exatamente esse conjunto que gera a lista de renovações urgentes.

Contagem de dias úteis: exclua sábados, domingos e os feriados de `{{calendario_feriados}}`; exiba a contagem quando o prazo for apertado. Se os feriados municipais do órgão não forem conhecidos, avise que o prazo pode recuar.

Certidões de habilitação profissional e de regularidade **do contador** valem 90 dias (Resolução CFC 1.637/2021) — confira-as junto com o balanço; sem elas o balanço fica atacável.

---

## Qualificação econômico-financeira — análise contábil (obrigatório)

### Fórmulas exatas (recalcule sempre; nunca aceite o índice declarado)

- **Liquidez Geral:** LG = (AC + RLP) ÷ (PC + PNC)
- **Liquidez Corrente:** LC = AC ÷ PC
- **Solvência Geral:** SG = Ativo Total ÷ (PC + PNC)
- **Capital Circulante Líquido:** CCL = AC − PC
- **Endividamento:** ET = (PC + PNC) ÷ Ativo Total

Onde AC = ativo circulante; RLP = realizável a longo prazo; ANC = ativo não circulante (inclui o RLP); PC = passivo circulante; PNC = passivo não circulante; PL = patrimônio líquido.

Confira também a identidade fundamental: **Ativo total = Passivo total + PL**. Balanço que não fecha é vício objetivo. Exiba a aritmética de cada índice com os valores lidos do balanço e a página de origem.

Padrão aceito: exigir **≥ 1,0**; índices superiores exigem justificativa técnica no processo. Índice exigido sem a fórmula no edital é impugnável (julgamento não objetivo). Uma "demonstração de índices" que declara LG usando a fórmula da Solvência Geral é erro recorrente e inverte completamente o resultado — recalcule sempre.

### Checklist de formalidades do balanço

1. **Exercício exigível:** último exercício social encerrado nos termos da lei. Regra prática: o prazo de entrega da ECD (SPED Contábil) vai até o último dia útil de maio do ano seguinte — antes disso pode ser aceitável o balanço do ano anterior; depois, não. Verifique o que o edital fixa.
2. **Autenticação:** livro diário com termos de abertura e encerramento registrado na Junta Comercial **ou** recibo de entrega da ECD/SPED (equivalente, Decreto 8.683/2016). Balanço "solto" é inabilitável quando o edital exige autenticação.
3. **Assinaturas:** contador com CRC ativo + representante legal.
4. **Empresa com menos de um exercício:** balanço de abertura é aceito.
5. **Vedado substituir balanço por balancete** provisório, salvo previsão expressa.
6. **ME/EPP:** ser optante do Simples não dispensa o balanço quando o edital o exige.

### Capital social e PL mínimo

- Teto legal: **10% do valor estimado** (art. 69, §1º). O edital deve exigir PL **ou** capital social — não os dois cumulativamente.
- O capital que conta é o **integralizado** (confira no contrato social / certidão da Junta; capital subscrito e não integralizado não conta).
- Compare o PL do balanço com o exigido e verifique se o PL declarado fecha com a própria composição do balanço (capital + reservas + resultados acumulados).

---

## Cruzamentos obrigatórios

1. **Validade na DATA DA SESSÃO**, nunca hoje — para cada certidão, recalcule.
2. **Capital social:** contrato social / certidão da Junta × balanço patrimonial × notas explicativas. Divergência (por exemplo, R$ 300.000 registrados na Junta convivendo com R$ 100.000 nos balanços) é vício que concorrente explora em recurso — corrigir com o contador **antes** de qualquer envio, e antes de atacar o capital de qualquer concorrente.
3. **Endereço:** contrato social × cartão CNPJ × cadastro de fornecedores (SICAF ou equivalente) × alvará × inscrição municipal × certidões × proposta. Após alteração contratual de sede, todo documento com endereço antigo precisa de reemissão. Editais federais costumam trazer cláusula punindo divergência cadastral com desclassificação — localize a cláusula equivalente neste edital.
4. **Jurisdição das certidões:** certidão de ações trabalhistas deve ser emitida pelo tribunal regional **da região do órgão licitante**; a de outra região não cobre. O mesmo raciocínio vale para certidões estaduais e municipais.
5. **Certidões do contador** (habilitação profissional + negativa de débitos no CRC): validade 90 dias. Sem elas, o balanço é atacável.
6. **Filiais:** se a empresa tiver filial e o edital exigir regularidade de todos os estabelecimentos, inclua as certidões da filial (CNPJ próprio).
7. **Razão social anterior em atestado:** atestado emitido sob razão social antiga é regular — a defesa é juntar a alteração contratual que prova a continuidade da pessoa jurídica. Verifique as alterações antes de apontar divergência.
8. **Atribuição profissional do RT × objeto:** o responsável técnico indicado precisa ter atribuição compatível (engenharia civil, mecânica, elétrica, TI, saúde, conforme o objeto), e o registro da empresa no conselho precisa contemplar o ramo correspondente.
9. **Acervo × exigência:** objeto, quantitativo, valor, contratante, período, RT e nº da CAT, todos **lidos do documento**.

---

## Protocolo pericial (obrigatório)

1. **Documento-fonte.** Nenhum ✅/🟥 sem o arquivo aberto e lido nesta análise. Dossiê, índice e nome de arquivo são mapa, não fonte; o que não foi lido sai como **"não verificado"**. Datas, nomes, CNPJs, endereços e valores conferem-se **dentro** do documento.
2. **Leitura integral.** Abrir todos os arquivos do caderno, inclusive os compactados. Em séries repetitivas grandes, ler amostra dirigida de cada série e declarar o que foi amostrado.
3. **Volume grande:** organize a leitura em lotes (15 a 20 arquivos por bloco), registrando o que já foi conferido, para poder retomar sem refazer.
4. **Todo número citado foi recalculado** e referenciado ao documento e à página de origem.
5. Em conflito entre resumo/dossiê e documento-fonte, **o documento-fonte prevalece sempre**.
