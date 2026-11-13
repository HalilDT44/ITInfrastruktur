$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force artifacts/scans | Out-Null
foreach ($name in @('web','api')) {
    $context = if ($name -eq 'web') { '.' } else { 'backend' }
    docker build -t "zendo-${name}:1.0.0" $context
    if ($LASTEXITCODE -ne 0) { throw 'Build fehlgeschlagen' }
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v zendo-trivy-cache:/root/.cache/trivy -v "${PWD}/artifacts/scans:/out" aquasec/trivy:latest image --quiet --scanners vuln --format json --output "/out/$name.json" --severity CRITICAL --exit-code 1 "zendo-${name}:1.0.0"
    if ($LASTEXITCODE -ne 0) { throw "Scan fehlgeschlagen oder kritische Schwachstellen in $name. Siehe artifacts/scans." }
}
