# Contabilidade aplicada à habilitação econômico-financeira

Guia prático para ANALISAR (e atacar/defender) a qualificação econômico-financeira em licitações — tanto os documentos da empresa cliente quanto os de concorrentes. Complementa a seção 7 da `jurisprudencia.md` e os arts. 65-70 da Lei 14.133/2021.

## 1. O balanço patrimonial — anatomia mínima

| Grupo | Conteúdo típico | Sigla |
|---|---|---|
| Ativo Circulante | caixa, bancos, aplicações, clientes/duplicatas, estoques, impostos a recuperar | AC |
| Ativo Não Circulante | realizável a longo prazo (RLP) + investimentos + imobilizado + intangível | ANC |
| Passivo Circulante | fornecedores, empréstimos de curto prazo, obrigações fiscais/trabalhistas | PC |
| Passivo Não Circulante | exigível a longo prazo | PNC (ELP) |
| Patrimônio Líquido | capital social + reservas + lucros/prejuízos acumulados | PL |

Identidade fundamental: **Ativo total = Passivo total + PL**. Balanço que não fecha é vício objetivo.

## 2. Índices usuais em edital — fórmulas exatas

- **Liquidez Geral:** LG = (AC + RLP) ÷ (PC + PNC)
- **Liquidez Corrente:** LC = AC ÷ PC
- **Solvência Geral:** SG = Ativo Total ÷ (PC + PNC)
- **Capital Circulante Líquido:** CCL = AC − PC (alguns editais exigem CCL ≥ x% do valor estimado)
- **Endividamento (menos comum):** ET = (PC + PNC) ÷ Ativo Total

Padrão aceito pelo TCU: exigir **≥ 1,0**; índices maiores exigem justificativa técnica (Acórdão 1.214/2013-Plenário). Edital deve trazer as fórmulas — índice sem fórmula no edital é impugnável (julgamento não objetivo).

**Sempre RECALCULE os índices a partir dos valores do balanço**, exibindo a aritmética com os valores lidos e a página de origem:

```
AC  = ativo circulante            PC  = passivo circulante
RLP = realizável a longo prazo    PNC = passivo não circulante (ELP)
ANC = ativo não circulante        PL  = patrimônio líquido
      (inclui o RLP)              AT  = ativo total (= AC + ANC)

LG  = (AC + RLP) / (PC + PNC)     LC  = AC / PC
SG  = AT / (PC + PNC)             CCL = AC − PC
ET  = (PC + PNC) / AT
```

Confira também a identidade **Ativo total = Passivo total + PL** — balanço que não fecha é vício objetivo. Nunca aceite o índice declarado na "demonstração de índices" do licitante sem recálculo: erro (ou maquiagem) aqui é achado recorrente. Já houve demonstração declarando Liquidez Geral de 1,45 aplicando a fórmula da Solvência Geral, quando o LG real era 0,57.

## 3. Formalidades do balanço — checklist de ataque/defesa

1. **Exercício exigível:** último exercício social encerrado nos termos da lei. Regra prática: prazo da ECD (SPED Contábil) vai até o último dia útil de MAIO do ano seguinte (IN RFB) — antes disso, pode ser aceitável o balanço do ano anterior; depois, não. Verifique o que o edital fixa.
2. **Autenticação:** livro diário com termos de abertura e encerramento, registrado na Junta Comercial — OU recibo de entrega da ECD/SPED (a autenticação via SPED equivale, Decreto 8.683/2016). Balanço "solto", sem diário nem SPED, é inabilitável se o edital exigiu autenticação.
3. **Assinaturas:** contador com CRC ativo + representante legal. Confira a Certidão de Habilitação Profissional e a negativa de débitos do contador — validade de 90 dias (Resolução CFC 1.637/2021); sem elas, o balanço fica atacável. Mantenha-as no dossiê da empresa cliente.
4. **Empresa nova (menos de 1 exercício):** balanço de abertura é aceito.
5. **É vedado substituir balanço por balancete** provisório, salvo previsão expressa.
6. **ME/EPP:** a LC 123 não dispensa balanço quando o edital o exige para obras — dispensas indevidas por "ser do Simples" são achado clássico contra concorrente.

## 4. PL / Capital social mínimo

- Teto legal: **10% do valor estimado** (art. 69, §1º). Edital deve exigir PL **ou** capital social mínimo — não os dois cumulativamente.
- Capital social a considerar é o **integralizado** (confira no contrato social/certidão da Junta — capital subscrito e não integralizado não conta; TCU já rejeitou capital "de fachada" aumentado dias antes da sessão sem lastro).
- Compare o PL do balanço do concorrente com o exigido — e cheque se o PL declarado bate com a conta do próprio balanço (capital + reservas + resultados).

## 5. Sinais de balanço "maquiado" de concorrente (indícios para aprofundar)

- Índices exatamente 1,00 ou redondos demais em todas as métricas.
- AC dominado por "outros créditos" genéricos ou estoques desproporcionais ao porte/atividade.
- PL alto com receita (DRE) irrisória — empresa de papel.
- Balanço sem SPED nem registro na Junta; termos de abertura/encerramento ausentes ou sem numeração de livro.
- Divergência entre capital social do balanço e o do contrato social/QSA.
- DRE incompatível com os atestados que a empresa apresenta (executou R$ 5 mi em obras com receita anual de R$ 300 mil?). Esse cruzamento DRE × atestados é um dos ataques mais eficazes em recurso.

> Indício não é prova. Em peça, formule como "inconsistência que impõe diligência" (art. 64 — diligências) e peça verificação, salvo quando o vício for formal e objetivo (aí é inabilitação direta).

## 6. Garantias (art. 96-102) — noções financeiras

- Garantia de proposta: até 1% do valor estimado (art. 58). Contratual: regra 5%, até 10% em alto risco (art. 98-99); seguro-garantia com cláusula de retomada em obras grandes.
- Modalidades: caução em dinheiro/títulos, seguro-garantia, fiança bancária — escolha do CONTRATADO, não do edital. Edital que impõe modalidade única é impugnável.
- Apólice de seguro-garantia de concorrente: confira vigência, tomador, valor segurado e se a seguradora tem certidão de regularidade na SUSEP.

## 7. Regra de ouro

Todo número citado em análise ou peça (índice, PL, total de balanço) deve ter sido **recalculado**, com a aritmética explícita exibida, e referenciado à página ou linha do documento de origem. Teses contábeis que citem acórdão seguem a mesma trava de verificação prévia das citações jurisprudenciais aplicada aos prompts de redação de peças.
