"""Run only in the local lab after importing zendo-api:1.0.1."""
import concurrent.futures, json, socket, ssl, subprocess, threading, time, urllib.request
from pathlib import Path
if subprocess.check_output(['kubectl','config','current-context'],text=True).strip()!='k3d-zendo-validation':raise SystemExit('Isolated validation cluster only')
original=socket.getaddrinfo;socket.getaddrinfo=lambda h,*a,**kw:original('127.0.0.1' if h=='zendo.local' else h,*a,**kw)
codes=[];versions=set();stop=False;ctx=ssl._create_unverified_context()
def traffic():
 while not stop:
    try:
        req=urllib.request.Request('https://zendo.local:8443/api/reports/generate',data=b'{}',headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,context=ctx,timeout=30) as r:codes.append(r.status if r.read().startswith(b'%PDF') else 0)
    except Exception:codes.append(0)
def k(*a):subprocess.run(['kubectl','-n','zendo',*a],check=True)
threads=[threading.Thread(target=traffic) for _ in range(4)]
for t in threads:t.start()
try:
    time.sleep(3);k('set','image','deployment/api','api=zendo-api:1.0.1');k('rollout','status','deployment/api','--timeout=180s');time.sleep(5)
    k('rollout','undo','deployment/api');k('rollout','status','deployment/api','--timeout=180s');time.sleep(3)
finally:
    stop=True
    for t in threads:t.join()
result={'report_requests':len(codes),'failed':sum(c!=200 for c in codes),'updated_image':'zendo-api:1.0.1','rolled_back':True}
Path('artifacts/rolling-update.json').write_text(json.dumps(result,indent=2));print(result);assert result['failed']==0
