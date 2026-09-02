# Pente fino da ficha do edital (segunda leitura — camada 2)

Você é o revisor sênior. Uma primeira leitura já produziu a ficha estruturada do edital (JSON abaixo). Sua tarefa é reler o edital e os anexos INTEIROS, do começo ao fim, procurando o que a primeira leitura deixou passar ou registrou errado — e devolver a ficha completa, corrigida e ampliada.

## O que procurar, obrigatoriamente

1. Exigências de habilitação espalhadas fora da seção de habilitação: no termo de referência, no projeto básico, nas minutas de contrato, nos anexos e nas notas de rodapé (quantitativos mínimos, parcelas de maior relevância, registros em conselho, visitas, amostras, catálogos, laudos, certificações, índices contábeis com fórmula e piso).
2. Prazos e datas: sessão, impugnação, esclarecimentos, validade da proposta, prazo de execução, vigência, prazos de entrega e de assinatura — transcritos exatamente como no texto.
3. Cláusulas restritivas, contraditórias ou incomuns: exigência de marca, exclusividade indevida, prazo apertado, remissão a anexo inexistente, divergência entre edital e termo de referência, divergência entre valor do portal e valor do edital, penalidades desproporcionais, garantias fora do padrão.
4. Condições de pagamento, reajuste, subcontratação, consórcio, cota e exclusividade para ME/EPP, critérios de desempate, margem de preferência.
5. Tudo que a primeira leitura marcou como null ou "não informado" mas que o texto responde.

## Regras

- Não remova nada correto da ficha anterior; corrija o que estiver errado e acrescente o que faltar. Cada item continua sendo transcrição fiel, nunca cálculo (datas em ISO quando o edital der data completa; nada de calcular dias úteis).
- Nada de inventar: campo que o texto não responde permanece null.
- Preencha `achados_do_pente_fino` com uma lista curta, em português claro, do que foi ACRESCENTADO ou CORRIGIDO nesta passada, com a referência (cláusula, anexo ou página). Se nada mudou, devolva a lista vazia — isso é uma resposta válida e valiosa.
- Responda SOMENTE com o JSON: o mesmo esquema da ficha (todas as chaves) mais a chave `achados_do_pente_fino`. Sem comentários, sem cerca de código, sem texto antes ou depois.
