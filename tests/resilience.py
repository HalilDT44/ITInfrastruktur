"""Destructive tests for the isolated zendo-validation lab only; restores replicas."""
import json, os, socket, ssl, subprocess, threading, time, urllib.request, urllib.error
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def k(*args):return subprocess.check_output(['kubectl',*args],text=True).strip()
if k('config','current-context')!='k3d-zendo-validation':raise SystemExit('Only permitted on isolated k3d-zendo-validation context.')
original=socket.getaddrinfo
socket.getaddrinfo=lambda host,*a,**kw:original('127.0.0.1' if host=='zendo.local' else host,*a,**kw)
ctx=ssl._create_unverified_context()
def get(path):
    try:
        with urllib.request.urlopen('https://zendo.local:8443'+path,context=ctx,timeout=10) as r:return r.status,r.read()
    except urllib.error.HTTPError as e:return e.code,e.read()
    except Exception:return 0,b''
results={}
for service in ['api','db']:
    kind='statefulset' if service=='db' else 'deployment'
    try:
        if service=='api':k('-n','zendo','delete','hpa','api','--ignore-not-found')
        k('-n','zendo','scale',kind+'/'+service,'--replicas=0')
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            code,body=get('/api/health')
            if code>=500:break
            time.sleep(2)
        results[service+'_outage']={'health_status':code,'frontend_status':get('/')[0]}
        time.sleep(60)  # Prometheus scrape, rule hold, Alertmanager group wait.
        results[service+'_alert_log']=k('-n','monitoring','logs','deployment/notifier','--since=3m')
    finally:
        k('-n','zendo','scale',kind+'/'+service,'--replicas='+('1' if service=='db' else '2'))
        k('-n','zendo','rollout','status',kind+'/'+service,'--timeout=180s')
        deadline=time.monotonic()+120
        while get('/api/health')[0]!=200 and time.monotonic()<deadline:time.sleep(2)
before=json.loads(get('/api/workspace')[1])
k('-n','zendo','delete','pod','db-0','--wait=false')
k('-n','zendo','wait','--for=condition=Ready','pod/db-0','--timeout=180s')
deadline=time.monotonic()+120
while get('/api/health')[0]!=200 and time.monotonic()<deadline:time.sleep(2)
results['workspace_survives_db_restart']=json.loads(get('/api/workspace')[1])==before
# Delete one frontend pod while repeatedly calling the web endpoint.
codes=[];stop=False
def traffic():
    while not stop:codes.append(get('/')[0]);time.sleep(.1)
t=threading.Thread(target=traffic);t.start()
pod=json.loads(k('-n','zendo','get','pods','-l','app.kubernetes.io/name=web','-o','json'))['items'][0]['metadata']['name']
k('-n','zendo','delete','pod',pod,'--wait=false');time.sleep(20);stop=True;t.join()
results['frontend_pod_loss']={'requests':len(codes),'failed':sum(c!=200 for c in codes)}
stack=json.loads((root/'k8s/stack.yaml').read_text())
hpa=next(o for o in stack['items'] if o['kind']=='HorizontalPodAutoscaler' and o['metadata']['name']=='api')
subprocess.run(['kubectl','apply','-f','-'],input=json.dumps(hpa),text=True,check=True)
(root/'artifacts/resilience.json').write_text(json.dumps(results,indent=2))
print({k:v for k,v in results.items() if not k.endswith('alert_log')})
assert all(results[s+'_outage']['health_status']>=500 and results[s+'_outage']['frontend_status']==200 for s in ['api','db'])
assert results['workspace_survives_db_restart'] and results['frontend_pod_loss']['failed']==0
