$ErrorActionPreference='Stop'
$checks=Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health?refresh=true' -TimeoutSec 45
$checks | ConvertTo-Json -Depth 10
