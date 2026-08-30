@echo off
REM Envia sua configuracao local (perfis, triagem) para a nuvem do GitHub.
REM Rode depois de criar/editar perfis, para o alerta diario usar as mudancas.
cd /d C:\busca_editais
git fetch origin main
git add data/radar.db
git commit -m "Configuracao atualizada no PC"
git push --force-with-lease origin main
if errorlevel 1 (
  echo.
  echo Falhou. Se pediu login, autorize no navegador e rode de novo.
) else (
  echo.
  echo Pronto! A proxima coleta da nuvem usa sua configuracao.
)
pause
