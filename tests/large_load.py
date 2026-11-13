"""Memory-bounded TLS load generator: streams 5 MiB per request from a shared chunk."""
import argparse, asyncio, hashlib, json, ssl, statistics, time
from pathlib import Path
from urllib.parse import urlsplit
p=argparse.ArgumentParser();p.add_argument('--url',default='https://zendo.local:8443');p.add_argument('--connect-host');p.add_argument('--requests',type=int,default=100);p.add_argument('--ramp',type=float,default=1);p.add_argument('--output',default='artifacts/large-stream.json');a=p.parse_args()
url=urlsplit(a.url);chunk=b'x'*65536;size=5*1024*1024;expected=hashlib.sha256(chunk*80).hexdigest();results=[]
async def send(i):
    await asyncio.sleep(i*a.ramp/a.requests)
    start=time.perf_counter();writer=None
    try:
        async with asyncio.timeout(180):
            reader,writer=await asyncio.open_connection(a.connect_host or ('127.0.0.1' if url.hostname=='zendo.local' else url.hostname),url.port or 443,ssl=ssl._create_unverified_context(),server_hostname=url.hostname,limit=65536)
            writer.write(f'POST /api/submissions HTTP/1.1\r\nHost: {url.netloc}\r\nContent-Type: application/octet-stream\r\nContent-Length: {size}\r\nConnection: close\r\n\r\n'.encode())
            for _ in range(80):writer.write(chunk);await writer.drain()
            head=await reader.readuntil(b'\r\n\r\n');code=int(head.split(b' ')[1]);body=await reader.read()
            # Chunked transfer encoding is decoded below when present.
            if b'transfer-encoding: chunked' in head.lower():
                decoded=bytearray()
                while body:
                    length,body=body.split(b'\r\n',1);n=int(length,16)
                    if n==0:break
                    decoded.extend(body[:n]);body=body[n+2:]
                body=bytes(decoded)
            value=json.loads(body) if code==200 else {}
            ok=code==200 and value.get('bytes')==size and value.get('sha256')==expected
            results.append({'status':code,'ok':ok,'seconds':time.perf_counter()-start})
    except Exception as e:results.append({'status':0,'ok':False,'error':str(e),'seconds':time.perf_counter()-start})
    finally:
        if writer:writer.close()
async def main():await asyncio.gather(*(send(i) for i in range(a.requests)))
start=time.perf_counter();asyncio.run(main());times=sorted(r['seconds'] for r in results)
report={'requests':a.requests,'ramp':a.ramp,'bytes_per_request':size,'elapsed':time.perf_counter()-start,'success':sum(r['ok'] for r in results),'p50':times[int(len(times)*.5)],'p95':times[min(len(times)-1,int(len(times)*.95))],'p99':times[min(len(times)-1,int(len(times)*.99))],'results':results}
Path(a.output).parent.mkdir(exist_ok=True,parents=True);Path(a.output).write_text(json.dumps(report,indent=2));print({k:v for k,v in report.items() if k!='results'})
raise SystemExit(report['success']!=a.requests)
