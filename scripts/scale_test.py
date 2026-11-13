import json, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def run(*args):subprocess.run(list(args),check=True,cwd=root)
run('kubectl','-n','zendo','delete','hpa','api','--ignore-not-found')
try:
    run('kubectl','-n','zendo','set','env','deployment/api','REPORT_CONCURRENCY=4')
    for count in [1,3]:
        run('kubectl','-n','zendo','scale','deployment/api',f'--replicas={count}')
        run('kubectl','-n','zendo','rollout','status','deployment/api','--timeout=180s')
        run('docker','run','--rm','--add-host','zendo.local:host-gateway','-v',f'{root}/tests:/tests:ro','-v',f'{root}/artifacts:/out','grafana/k6:latest','run','--quiet','-e',f'OUTPUT=/out/report-{count}.json','/tests/report_scale.js')
finally:
    run('kubectl','-n','zendo','set','env','deployment/api','REPORT_CONCURRENCY-')
    stack=json.loads((root/'k8s/stack.yaml').read_text())
    hpa=next(o for o in stack['items'] if o['kind']=='HorizontalPodAutoscaler' and o['metadata']['name']=='api')
    subprocess.run(['kubectl','apply','-f','-'],input=json.dumps(hpa),text=True,check=True)
    run('kubectl','-n','zendo','scale','deployment/api','--replicas=2')
