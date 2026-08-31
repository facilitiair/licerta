# Montagem da Proposta e Checklist de Participação

Este prompt produz dois entregáveis a partir de um edital: (1) o **checklist de envio** — todos os documentos de habilitação e de proposta exigidos, com status, arquivo de origem no dossiê da empresa cliente e ações pendentes em ordem de urgência; e (2) o **esqueleto da proposta comercial** — estrutura da carta-proposta e dos documentos que a acompanham, conforme o modelo e as exigências de forma do edital. Não define preços: preço é decisão do cliente.

## Entradas

- `{{edital_texto}}` — edital, Termo de Referência / Projeto Básico, planilha orçamentária, modelos anexos e minuta de contrato.
- `{{ficha_edital}}` — número, órgão, objeto, valor estimado, plataforma de envio, **data e hora da sessão** e prazo-limite de entrega.
- `{{dossie_empresa}}` — dossiê da empresa cliente, com o identificador de cada documento no acervo (para que o cliente localize rapidamente), validades, acervo técnico, responsáveis técnicos, cadastros, declarações padrão, modelos timbrados e garantias disponíveis.
- `{{documentos_do_caso}}` — documentos efetivamente abertos e lidos.
- `{{status_habilitacao}}` — resultado da checagem de habilitação, se já realizada (status por exigência).
- `{{data_de_hoje}}`
- `{{calendario_feriados}}`
- `{{base_juridica}}` — Lei 14.133/2021, jurisprudência (com atenção às teses de BDI e de exequibilidade) e glossário.

---

## Procedimento

### Passo 1 — confirmar pré-requisitos

Verifique se o edital já foi analisado e se a habilitação já foi checada. Se `{{status_habilitacao}}` estiver vazio, execute primeiro a checagem de habilitação — o checklist de envio depende dela.

### Passo 2 — montar o CHECKLIST DE ENVIO

```
# CHECKLIST DE ENVIO — [Nº do edital] / [Órgão]
Data e hora limite de entrega: [data] | Sessão: [data] | Dias úteis restantes: [X]

## PARTE 1 — Documentos de Habilitação
(status vindos da checagem de habilitação)

### Habilitação Jurídica
- [ ] Contrato social consolidado e alterações — ARQUIVO: [ref no dossiê]
- [ ] Cartão CNPJ atualizado — ARQUIVO: [ref] (emissão [data])
- [ ] Quadro de sócios e administradores — ARQUIVO: [ref]
- [ ] Documento de identificação do representante legal — ARQUIVO: [ref]
- ...

### Habilitação Técnica
- [ ] Registro da empresa no conselho profissional — ARQUIVO: [ref]
- [ ] Registro do(s) responsável(is) técnico(s) — ARQUIVO: [ref]
- [ ] Atestado de capacidade técnica compatível [indicar QUAL atestado do acervo atende] — ARQUIVO: [ref]
- [ ] CAT correspondente ao atestado indicado — ARQUIVO: [ref]
- [ ] Declaração de equipe técnica — ARQUIVO: [ref]
- [ ] Comprovação de vínculo do RT (contrato social, CLT ou contrato de prestação de serviços) — ARQUIVO: [ref]
- [ ] [se o atestado trouxer razão social anterior] Alteração contratual que prova a continuidade — ARQUIVO: [ref]

### Habilitação Fiscal, Social e Trabalhista
[listar todas as certidões exigidas, com status, validade e arquivo]

### Habilitação Econômico-Financeira
- [ ] Balanço patrimonial do exercício exigível, autenticado — ARQUIVO: [ref]
- [ ] Demonstração dos índices exigidos, com as fórmulas do edital — ARQUIVO: [ref]
- [ ] Certidões do contador (habilitação profissional e negativa — 90 dias) — ARQUIVO: [ref]
- [ ] [se exigido] Comprovação de capital social ou PL mínimo — conferir contra o contrato social e o balanço
- [ ] [se exigida] Garantia de proposta — providenciar apólice/caução vinculada a ESTE certame

### Idoneidade e regularidade complementar
[listar as consultas e certidões exigidas pelo edital, com status e arquivo]

### Declarações específicas exigidas pelo edital
[listar uma a uma — usar os modelos do dossiê como base, mas gerar versão nova para este certame]

## PARTE 2 — Proposta Comercial
- [ ] Planilha orçamentária preenchida (modelo do edital, se houver)
- [ ] Composições analíticas de custo unitário, quando exigidas
- [ ] Composição de encargos sociais
- [ ] Detalhamento do BDI conforme o edital
- [ ] Cronograma físico-financeiro
- [ ] Declaração de elaboração independente da proposta
- [ ] Carta-proposta com timbre e assinatura — ARQUIVO base: [modelo timbrado do dossiê]
- [ ] [se exigido] Atestado de visita técnica ou declaração de pleno conhecimento das condições locais
- [ ] [se exigida] Anotação de responsabilidade técnica

## PARTE 3 — Forma de envio
- Plataforma: [portal indicado no edital]
- Credenciamento/cadastro exigido: [qual]
- Data e hora de abertura:
- Tempo restante:
- Formato e tamanho máximo dos arquivos, exigência de assinatura digital: [conforme o edital]

## AÇÕES PENDENTES (em ordem de urgência)
1. [renovar a certidão X até o dia Y — órgão emissor Z]
2. [emitir a anotação de responsabilidade técnica para este objeto]
3. [gerar as declarações com o número deste edital e o órgão corretos]
4. ...
```

### Passo 3 — esqueleto da PROPOSTA COMERCIAL

Gere a estrutura da carta-proposta a partir do modelo timbrado disponível no dossiê, adaptando:

- Cabeçalho: razão social, CNPJ, endereço **atual**, contato
- Identificação do edital (número, modalidade, órgão, processo administrativo)
- Objeto exato como descrito no edital
- Valor global em algarismos e por extenso (a ser preenchido pelo cliente)
- Prazo de validade da proposta (mínimo de 60 dias se o edital for silente)
- Prazo de execução e cronograma
- Declaração de conformidade (atendimento de todas as exigências do edital e anexos)
- Declaração de que no preço estão inclusos todos os tributos, encargos, insumos e despesas
- Dados bancários, quando exigidos
- Local, data e assinatura do representante legal

### Passo 4 — revisão final antes do envio

Antes de encerrar, registre os pontos de verificação:

- nenhuma certidão vence entre hoje e a data da sessão;
- a planilha de custos fecha com o valor global da carta-proposta;
- BDI e encargos sociais estão dentro dos limites do edital e coerentes entre planilha e detalhamento;
- todas as declarações citam o número deste edital e este órgão **dentro do texto**;
- endereço atual em todos os documentos, inclusive proposta, declarações e cadastro de fornecedores;
- cópia em PDF de tudo salva antes do upload;
- conferência final do caderno executada (veredito "PRONTO PARA ENVIAR: SIM/NÃO").

---

## Regras

- **Use o identificador de cada documento no dossiê** para que o cliente localize o arquivo rapidamente.
- **Distinga obrigatório de recomendado.** Documentos "que ajudam" não podem ser misturados aos exigidos.
- **Nunca preencha valores comerciais.** Preço, margem e estratégia de lance são decisão do cliente; este prompt estrutura o documento e verifica conformidade.
- **Certidão vencida nunca é ✅** — marque 🟥 com "vencida em DD/MM/AAAA — renovar antes da sessão" e inclua a renovação nas ações pendentes.
- **Escreva as ações para quem é iniciante:** órgão emissor, onde se solicita, tempo típico de emissão.

---

## Conferência pré-envio (obrigatória antes de dar o checklist por concluído)

1. **Declarações amarradas a ESTE certame.** Cada declaração deve citar o número do certame e o órgão corretos **dentro** do texto. Reaproveitar declaração de outro edital é declaração falsa (art. 155, VIII). Gere novas, sempre.
2. **Garantia de proposta vinculada a este certame:** apólice ou caução citando este edital e este órgão, valor ≥ o exigido, vigência cobrindo a validade da proposta.
3. **Endereço atual em todos os documentos** — proposta, declarações, cadastro de fornecedores, cartão CNPJ, alvará, inscrição municipal e certidões. Após alteração contratual de sede, o que ficou com endereço antigo precisa de reemissão.
4. **Atestado escolhido + CAT correspondente + RT com atribuição compatível com o objeto** (obra civil, instalações, engenharia mecânica, TI, saúde, fornecimento — cada objeto pede a habilitação profissional correta), acrescida da alteração contratual quando o atestado trouxer razão social anterior.
5. **Forma exigida para cada documento** (assinatura digital, firma reconhecida, autenticação, modelo obrigatório) conferida contra a cláusula do edital, não presumida.

---

## Protocolo pericial (obrigatório)

1. **Documento-fonte.** Nenhum ✅/🟥 sem que o arquivo tenha sido aberto e lido nesta análise. Dossiê, índice e nome de arquivo são mapa, não fonte; o que não foi lido sai como **"não verificado"**.
2. **Leitura integral.** Todos os arquivos do caderno, inclusive os compactados; datas, nomes, CNPJs, endereços e valores conferidos **dentro** do documento.
3. **Validades se aferem na data da sessão**, com a contagem de dias úteis exibida.
4. Em conflito entre resumo/dossiê e documento-fonte, **o documento-fonte prevalece sempre**.
