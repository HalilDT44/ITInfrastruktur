"""Full assessment matrix using containerized k6; no host k6 needed."""
import argparse, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base-url',default='https://zendo.local:8443');p.add_argument('--network');p.add_argument('--loadbalancer');p.add_argument('--soak-only',action='store_true');p.add_argument('--skip-soak',action='store_true');a=p.parse_args()
if a.network and a.base_url=='https://zendo.local:8443':a.base_url='https://zendo.local'
network_args=[]
if a.network:
    if not a.loadbalancer:raise SystemExit('--network requires --loadbalancer')
    ip=subprocess.check_output(['docker','inspect','-f','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',a.loadbalancer],text=True).strip()
    network_args=['--network',a.network,'--add-host','zendo.local:'+ip]
root=Path(__file__).resolve().parents[1];out=root/'artifacts/load';out.mkdir(parents=True,exist_ok=True)
cases=[] if a.soak_only else [(m,n,r,False) for m in ['web','normal','large'] for n,r in [(10,0),(100,1),(1000,5)]]+[('web',1000,1,False)]
if not a.skip_soak:cases.append(('web',0,0,True))
results=[]
for mode,n,r,soak in cases:
    name='web-soak' if soak else f'{mode}-{n}-{r}'
    cmd=['docker','run','--rm','--add-host','zendo.local:host-gateway','-v',f'{root}/tests:/tests:ro','-v',f'{out}:/out','grafana/k6:latest','run','--quiet','-e',f'BASE_URL={a.base_url}','-e',f'MODE={mode}','-e',f'VUS={n}','-e',f'RAMP={r}','-e',f'SOAK={int(soak)}','-e',f'OUTPUT=/out/{name}.json','/tests/load.js']
    if a.network:cmd=cmd[:3]+network_args+cmd[5:]
    if mode=='large':
        cmd=['python',str(root/'tests/large_load.py'),'--url',a.base_url,'--requests',str(n),'--ramp',str(r),'--output',str(out/(name+'.json'))]
    if mode=='large' and a.network:
        cmd=['docker','run','--rm',*network_args,'-v',f'{root}/tests:/tests:ro','-v',f'{out}:/out','--entrypoint','python','zendo-api:1.0.0','/tests/large_load.py','--url',a.base_url,'--connect-host',a.loadbalancer,'--requests',str(n),'--ramp',str(r),'--output',f'/out/{name}.json']
    print(f'Start {name}',flush=True)
    with (out/(name+'.log')).open('w') as f:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
    results.append({'case':name,'exit_code':code});print(f'{name}: exit {code}',flush=True)
    (out/('soak-results.json' if a.soak_only else 'matrix-results.json')).write_text(json.dumps(results,indent=2))
raise SystemExit(any(r['exit_code'] for r in results))
