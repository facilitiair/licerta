"""Agenda todos os jobs. Rodar como processo separado do web.

| job                   | frequência                     |
|-----------------------|--------------------------------|
| capturar_pncp         | a cada 2h                      |
| analisar_edital       | fila (disparo pela captura)    |
| detectar_republicacao | junto da captura               |
| matching_radar        | após captura                   |
| digest_diario         | 06h30                          |
| ler_emails            | a cada 5 min                   |
| vigiar_validades      | 1x/dia                         |
| vigiar_fases          | a cada 30 min (dias de sessão) |
| processar_atas        | 1x/dia                         |
| prever_horario        | manhã de dias com sessão       |
| watchdog              | a cada 15 min                  |
"""
