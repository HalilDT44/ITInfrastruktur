param([string]$BaseUrl = 'https://zendo.local:8443')
$ErrorActionPreference = 'Stop'
python scripts/load_docker.py --base-url $BaseUrl
if ($LASTEXITCODE -ne 0) { throw 'Mindestens ein Lastfall fehlgeschlagen. Siehe artifacts/load.' }
