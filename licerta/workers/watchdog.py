"""Monitor do próprio pipeline — a peça que empreendedor solo mais esquece.

Checa a cada 15 min e avisa o Paulo no WhatsApp se:
- captura de editais zerada vs média móvel dos últimos 7 dias
- taxa de parse de e-mail/ata caindo
- campos nulos em massa nas fichas
- fila travada / jobs sem execução no horário esperado
Falha silenciosa = cliente perdendo pregão sem ninguém saber.
"""
