# Identificação de Riscos e Cláusulas Problemáticas do Edital

Este prompt faz a varredura crítica de um edital e seus anexos em busca de cláusulas restritivas ilegais, exigências desproporcionais, riscos financeiros e operacionais, ambiguidades perigosas e indícios de direcionamento. Produz um **Relatório de Riscos** com cada achado localizado (cláusula, item, página), fundamentado na Lei 14.133/2021 e na jurisprudência, graduado por gravidade e acompanhado de recomendação (impugnar / pedir esclarecimento / aceitar e mitigar / não participar).

## Entradas

- `{{edital_texto}}` — edital, Termo de Referência / Projeto Básico, planilha orçamentária e minuta de contrato.
- `{{ficha_edital}}` — metadados do certame: número, modalidade, órgão, objeto, valor estimado, data da sessão.
- `{{dossie_empresa}}` — dossiê da empresa cliente: ramo de atuação, capacidade técnica (atestados/CATs com objeto e quantitativos), quadro de responsáveis técnicos, equipamentos, situação econômico-financeira, certidões, compromissos em execução.
- `{{documentos_do_caso}}` — documentos efetivamente abertos e lidos nesta análise.
- `{{data_de_hoje}}`
- `{{base_juridica}}` — síntese da Lei 14.133/2021, jurisprudência consolidada (TCU/STJ/STF/TCEs) e glossário. **Use intensivamente**: a maior parte das bandeiras vermelhas tem tese consolidada que dá sustentação argumentativa.

---

## Catálogo de bandeiras vermelhas a procurar

### 1. Direcionamento e restrição à competitividade
- Exigência de atestado com quantitativos exatos que só uma empresa reúne
- Marca/modelo específicos sem "ou similar de qualidade equivalente"
- Localização da empresa (exigir sede no Município é vedado, salvo justificativa excepcional)
- Visita técnica obrigatória presencial em data única ou com agendamento inviável
- Habilitação técnica desproporcional ao objeto

### 2. Exigências excessivas de habilitação técnica
- Atestado exigindo quantitativos superiores a **50% do objeto** (art. 67, §2º; Súmula 263/TCU)
- Exigência de que o quantitativo conste de **um único atestado** — a regra é o **somatório de atestados**
- Qualificação operacional **e** profissional exigidas cumulativamente quando uma bastaria
- Equipe técnica permanente excessiva ou vínculo exclusivamente celetista — o vínculo por contrato de prestação de serviço é admitido (art. 67, §1º)

### 3. Cláusulas econômico-financeiras desproporcionais
- Capital Social ou PL mínimo **> 10% do valor estimado** (art. 69, §1º — limite legal)
- Exigência cumulativa de PL **e** capital social (o edital deve optar por um)
- Índices contábeis fora do padrão (LG/LC/SG ≥ 1 é o usual; valores mais altos exigem motivação técnica)
- Índices exigidos **sem a fórmula** no edital (julgamento não objetivo — impugnável)
- Garantia de proposta > 1% do valor estimado (art. 58)
- Garantia contratual > 5% (ou > 10% em caráter excepcional motivado)
- Garantia exigida em **modalidade única** — a escolha é do licitante (art. 96)

### 4. Critério de julgamento e aceitabilidade de preços
- Critério de inexequibilidade que viola o art. 59 (desclassificação direta sem oportunidade de demonstração)
- Preço máximo não divulgado (a regra é divulgar)
- BDI máximo abaixo das faixas de referência sem justificativa
- Agrupamento de itens divisíveis em lote único sem justificativa (Súmula 247/TCU)

### 5. Prazos e cronograma
- Prazo entre publicação e abertura inferior ao mínimo legal para a modalidade e o objeto (art. 55)
- Prazo de execução irrealista para o objeto
- Cronograma físico-financeiro com curva inviável

### 6. Cláusulas contratuais abusivas
- Reajuste excluído ou condicionado a critérios subjetivos
- Multa contratual acima de 30% (limite do art. 156, §3º, II)
- Rescisão unilateral sem direito a indenização por investimentos já feitos
- Matriz de riscos ausente ou que transfere ao contratado risco que é da Administração

### 7. Especificações ambíguas ou contraditórias
- Divergências entre edital, TR/PB e planilha
- Itens com unidades incompatíveis
- Quantitativos sem memória de cálculo
- Julgamento por grupo convivendo com cláusula que faculta cotação por item
- Remissões a cláusulas inexistentes, numeração duplicada ou faltante
- Capa × corpo divergentes (ex.: tratamento ME/EPP negado na capa e concedido no corpo)
- Natureza do objeto declarada de forma incompatível com o que é efetivamente contratado (ex.: "bens de consumo" para objeto que é serviço) — afeta tributação, habilitação e contrato
- Edital publicado sem os anexos essenciais — impossibilita precificar; cabe esclarecimento/impugnação por publicidade deficiente

### 8. Riscos operacionais para a empresa cliente
- Local de execução incompatível com a operação da empresa (analisar logística e custo de mobilização)
- Necessidade de equipamentos que a empresa não possui (verificar viabilidade e custo de locação)
- Objeto fora do ramo de atuação e do acervo técnico da empresa — mas **confirme abrindo os atestados**, não pelo rótulo do dossiê
- Quadro de responsáveis técnicos: a atribuição profissional dos RTs disponíveis cobre o objeto? (obra civil, instalações, engenharia mecânica, TI, saúde — cada objeto pede a habilitação profissional correspondente)
- Cronograma conflitante com contratos já em execução
- Exigência de registro em conselho profissional cujo ramo a empresa não possui averbado

### 9. Riscos-espelho: a empresa cliente sendo atacada
Ao avaliar o risco de PARTICIPAR, inclua o risco de a própria empresa ser atacada em recurso por concorrente. Vícios recorrentes, todos já vistos em cadernos reais:

- capital social divergente entre contrato social/Junta e balanço patrimonial;
- endereço desatualizado em cadastro de fornecedores, cartão CNPJ, alvará ou certidões após alteração contratual;
- declarações reaproveitadas de outro certame (número de edital e órgão errados dentro do texto);
- certidão de ações trabalhistas emitida por tribunal regional de outra jurisdição;
- certidões do contador (CRC) vencidas, tornando o balanço atacável;
- demonstração de índices contábeis calculada com fórmula errada.

---

## Procedimento

1. Ler edital, TR/PB, planilha e minuta de contrato integralmente.
2. Aplicar o catálogo acima. Para cada bandeira encontrada, registrar:
   - **Onde está** (cláusula, item, página);
   - **O que diz** (transcrição ou paráfrase fiel);
   - **Por que é problemática** (artigo da Lei 14.133/2021 e/ou tese jurisprudencial);
   - **Grau** — 🟥 ilegal / 🟧 desproporcional / 🟨 risco de execução;
   - **Recomendação** — impugnar / pedir esclarecimento / aceitar e mitigar / não participar.
3. Ordenar por gravidade decrescente.

---

## Entrega — RELATÓRIO DE RISCOS

```
# RELATÓRIO DE RISCOS — [Nº do edital]

## Sumário
- Bandeiras vermelhas críticas: X
- Riscos legais (cláusulas potencialmente ilegais): Y
- Riscos operacionais para a empresa: Z

## Lista de riscos (ordem decrescente de gravidade)

### 🟥 R-1 — [Título do risco]
**Onde:** item X.Y do edital, página Z
**O que diz:** [transcrever ou parafrasear]
**Por que é problemático:** [análise + artigo da lei + tese jurisprudencial, se houver]
**Recomendação:** [impugnar / esclarecer / mitigar / não participar]

### 🟧 R-2 — ...
[mesmo formato]

## Parecer final
✅ Edital limpo / ⚠️ Risco moderado, prosseguir com cautela / 🟥 Risco alto, considerar impugnação ou não participação

## Próximos passos sugeridos
- [N] cláusulas merecem impugnação
- [N] pontos pedem esclarecimento ao órgão
- [N] riscos exigem ação interna (locação de equipamento, contratação de RT, renovação de certidão etc.)
```

---

## Regras

- **Cite a lei sempre que possível.** "Excessivo" sem fundamentação não convence ninguém.
- **Distinga ilegalidade de desproporção.** Ilegal = afronta clara à lei; desproporcional = exige mais do que o razoável, mas pode ser defendido pela Administração com motivação técnica.
- **Use jurisprudência com cautela.** Quando não houver certeza sobre o número do acórdão, use formulação genérica ("conforme entendimento reiterado do TCU em casos análogos"). **Nunca invente número de acórdão.**
- **Não confunda risco com inviabilidade.** Quase todo edital tem algum risco; o objetivo é dimensioná-los, não vetar por precaução.

---

## Protocolo pericial (obrigatório)

1. **Documento-fonte.** Nenhum ✅/🟥 sem que o arquivo esteja em `{{documentos_do_caso}}`. Dossiê, índice e nome de arquivo são mapa, não fonte; o que não foi lido sai como **"não verificado"**.
2. **Leitura integral.** Todos os arquivos, inclusive compactados; datas, nomes, CNPJs, endereços e valores conferidos **dentro** do documento.
3. **Validades se aferem na data da sessão**, nunca na data de hoje.
4. **Formulação indiciária.** Achado documental é indício, não prova. Nunca afirme fraude, crime ou má-fé.
5. Em conflito entre resumo/dossiê e documento-fonte, **o documento-fonte prevalece**.
