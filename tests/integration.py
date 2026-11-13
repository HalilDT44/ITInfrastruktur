"""Run against Docker or Kubernetes: python tests/integration.py [base-url]."""
import concurrent.futures, hashlib, json, ssl, sys, time, urllib.request, urllib.error, socket, os
base=sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8080'
ctx=ssl._create_unverified_context()
if os.getenv('ZENDO_RESOLVE_LOCAL')=='1':
    original_getaddrinfo=socket.getaddrinfo
    socket.getaddrinfo=lambda host,*a,**kw:original_getaddrinfo('127.0.0.1' if host=='zendo.local' else host,*a,**kw)
def request(path,method='GET',data=None,content='application/json'):
    r=urllib.request.Request(base+path,data=data,method=method,headers={'Content-Type':content})
    try:
        with urllib.request.urlopen(r,context=ctx,timeout=120) as response:return response.status,response.read()
    except urllib.error.HTTPError as e:return e.code,e.read()
assert request('/')[0]==200
assert request('/api/live')[0]==200
assert request('/api/health')[0]==200
code,raw=request('/api/workspace');initial=json.loads(raw)
assert code==200
# Re-save the original workspace; no user data is removed by this test.
code,raw=request('/api/workspace','PUT',json.dumps(initial).encode());assert code==200,(code,raw)
assert request('/api/workspace','PUT',json.dumps(initial).encode())[0]==409
payload=b'x'*(5*1024*1024)
def submit(_):
    code,raw=request('/api/submissions','POST',payload,'application/octet-stream')
    result=json.loads(raw)
    assert code==200 and result['bytes']==len(payload) and result['sha256']==hashlib.sha256(payload).hexdigest()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:list(executor.map(submit,range(10)))
start=time.monotonic();code,pdf=request('/api/reports/generate','POST',b'{}')
assert code==200 and pdf.startswith(b'%PDF') and time.monotonic()-start>=1
print('PASS: Web, Liveness/Readiness, Workspace read/write, optimistic locking, 10 concurrent 5-MiB submissions, real PDF >= 1 second.')
