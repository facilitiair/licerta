# Cria a tarefa agendada que roda o radar todo dia às 08:00.
# Se o PC estiver desligado no horário, roda assim que ligar (StartWhenAvailable).
$python = (Get-Command python).Source
$acao = New-ScheduledTaskAction -Execute $python -Argument "radar.py" -WorkingDirectory "C:\busca_editais"
$gatilho = New-ScheduledTaskTrigger -Daily -At 08:00
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "RadarEditais" -Action $acao -Trigger $gatilho -Settings $config -Force
Write-Host "Tarefa 'RadarEditais' criada: radar diário às 08:00."
