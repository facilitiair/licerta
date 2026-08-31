@echo off
REM Envia sua configuracao local (perfis, alertas, triagem) para a nuvem.
REM Rode depois de criar/editar perfis, para a nuvem usar as mudancas.
REM
REM Por que nao usa mais "push --force-with-lease": o "git fetch" logo antes
REM atualiza a referencia que a trava confere, entao a trava sempre passava e
REM o push apagava os commits que o robo da nuvem tinha feito na madrugada.
REM Agora o HEAD e reposicionado sobre o remoto mantendo o SEU banco, e o
REM push vira um avanco normal: nada some do historico.
cd /d C:\busca_editais

REM Primeiro puxa do site os perfis mais novos (o site e o lugar de editar).
REM Se o site estiver fora do ar, segue com o que tem — so avisa.
python -m app.sincronizar

git fetch origin main
if errorlevel 1 goto falhou

git reset --soft origin/main
if errorlevel 1 goto falhou

git add data/radar.db
git diff --cached --quiet
if not errorlevel 1 (
  echo.
  echo Nada mudou desde o ultimo envio. Ja esta tudo na nuvem.
  goto fim
)

git commit -m "Configuracao atualizada no PC"
if errorlevel 1 goto falhou

git push origin main
if errorlevel 1 goto falhou

echo.
echo Pronto! A proxima coleta da nuvem usa sua configuracao.
goto fim

:falhou
echo.
echo Falhou. Se pediu login, autorize no navegador e rode de novo.

:fim
pause
