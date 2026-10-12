param([switch]$KeepMilvus)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path $PSScriptRoot -Parent
& (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $taskRoot 'scripts\stop-managed.py')
$owned=Get-NetTCPConnection -State Listen -LocalPort 8000,8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
$targets=@($owned | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$_" }) | Where-Object { $_.CommandLine -match 'uvicorn traceforge.api:app|traceforge.mcp_servers docs' }
foreach($process in $targets) { Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue }
if(-not $KeepMilvus){
 wsl -d Ubuntu -u root -- docker compose -p traceforge -f /mnt/d/systemDir/Documents/ChatGPT/agent_program/scripts/compose.yaml stop
 if(Test-Path (Join-Path $taskRoot 'data\demo-secrets.env')) { wsl -d Ubuntu -u root -- docker compose -p traceforge-demos --env-file /mnt/d/systemDir/Documents/ChatGPT/agent_program/data/demo-secrets.env -f /mnt/d/systemDir/Documents/ChatGPT/agent_program/scripts/demo-compose.yaml stop }
}
if(Test-Path (Join-Path $taskRoot 'data\processes.json')){
 $record=Get-Content (Join-Path $taskRoot 'data\processes.json') -Raw | ConvertFrom-Json
 foreach($id in @($record.backend,$record.mcp)){
  $process=Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
  if($process -and $process.CommandLine -match 'uvicorn traceforge.api:app|traceforge.mcp_servers docs'){Stop-Process -Id $id -ErrorAction SilentlyContinue}
 }
 if(-not $KeepMilvus -and $record.wsl){
  $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($record.wsl)" -ErrorAction SilentlyContinue
  if($process -and $process.CommandLine -match 'sleep infinity'){Stop-Process -Id $record.wsl -ErrorAction SilentlyContinue}
 }
}
Write-Host 'TraceForge服务已停止，数据与模型保留。'
