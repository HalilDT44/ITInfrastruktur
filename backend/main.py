import asyncio
import hashlib
import io
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from xml.sax.saxutils import escape

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

pool = None
requests = Counter('zendo_requests_total', 'HTTP requests', ['method', 'route', 'status'])
latency = Histogram('zendo_request_seconds', 'HTTP latency', ['route'], buckets=(.01,.05,.1,.5,1,2,3,5,10,30,60))
active = Gauge('zendo_active_requests', 'Active HTTP requests')
db_up = Gauge('zendo_database_up', 'Database reachable')
report_slots = asyncio.Semaphore(int(os.getenv('REPORT_CONCURRENCY', '16')))

@asynccontextmanager
async def lifespan(app):
    global pool
    password = Path(os.getenv('DB_PASSWORD_FILE', '/run/secrets/db_password')).read_text().strip()
    for attempt in range(60):
        try:
            pool = await asyncpg.create_pool(host=os.getenv('DB_HOST','db'), user='zendo', database='zendo', password=password, min_size=1, max_size=int(os.getenv('DB_POOL_SIZE','10')), command_timeout=10)
            async with pool.acquire() as c:
                await c.execute('CREATE TABLE IF NOT EXISTS workspace (id integer PRIMARY KEY CHECK (id=1), version bigint NOT NULL DEFAULT 0, data jsonb NOT NULL)')
                await c.execute('CREATE TABLE IF NOT EXISTS submissions (id bigserial PRIMARY KEY, received_at timestamptz DEFAULT now(), bytes integer NOT NULL, sha256 text NOT NULL)')
                await c.execute("INSERT INTO workspace (id,data) VALUES (1,'{\"projects\":[],\"tasks\":[]}') ON CONFLICT DO NOTHING")
            break
        except (OSError, asyncpg.PostgresError):
            if attempt == 59: raise
            await asyncio.sleep(2)
    yield
    await pool.close()

app = FastAPI(lifespan=lifespan)

@app.middleware('http')
async def metrics(request, call_next):
    start = time.monotonic()
    active.inc()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except (asyncpg.PostgresError, OSError, asyncio.TimeoutError):
        db_up.set(0)
        status = 503
        return JSONResponse({'detail':'Datenbank derzeit nicht erreichbar. Bitte später erneut versuchen.'}, status_code=503)
    finally:
        route = request.scope.get('route')
        path = route.path if route else 'unmatched'
        requests.labels(request.method,path,status).inc()
        latency.labels(path).observe(time.monotonic()-start)
        active.dec()

@app.get('/api/live')
async def live(): return {'status':'alive','version':os.getenv('APP_VERSION','1.0.0')}

@app.get('/api/health')
@app.get('/api/ready')
async def ready():
    try:
        async with asyncio.timeout(3):
            await pool.fetchval('SELECT 1')
        db_up.set(1)
        return {'status':'ready','database':'up'}
    except Exception:
        db_up.set(0)
        return JSONResponse({'status':'unavailable','database':'down'},status_code=503)

@app.get('/metrics')
async def metrics_endpoint():
    await ready()
    return Response(generate_latest(), headers={'Content-Type':CONTENT_TYPE_LATEST})

@app.get('/api/workspace')
async def workspace():
    row = await pool.fetchrow('SELECT data,version FROM workspace WHERE id=1')
    return {**json.loads(row['data']), 'version':row['version']}

async def body_limited(request, limit=6*1024*1024):
    result = bytearray()
    async for chunk in request.stream():
        result.extend(chunk)
        if len(result)>limit: raise HTTPException(413,'Request zu groß (max. 6 MiB).')
    return bytes(result)

@app.put('/api/workspace')
async def update_workspace(request: Request):
    try:
        payload = json.loads(await body_limited(request))
        version = payload.pop('version')
        if not isinstance(version,int) or not isinstance(payload['projects'],list) or not isinstance(payload['tasks'],list): raise ValueError()
        projects = payload['projects']; tasks = payload['tasks']
        if len(projects)>1000 or len(tasks)>20000: raise ValueError()
        ids = {p['id'] for p in projects}
        if len(ids)!=len(projects): raise ValueError()
        for p in projects:
            if not isinstance(p['name'],str) or not p['name'].strip() or p['color'] not in ['#7c69da','#55a38f','#dc9a64','#7098c9','#c87dac']: raise ValueError()
        for t in tasks:
            if t['projectId'] not in ids or t['status'] not in ['todo','progress','review','done'] or t['priority'] not in ['high','medium','low'] or not t['title'].strip(): raise ValueError()
        if len({t['id'] for t in tasks}) != len(tasks): raise ValueError()
        payload = {'projects':projects,'tasks':tasks}
    except (ValueError,KeyError,TypeError,AttributeError): raise HTTPException(422,'Ungültige Workspace-Daten.')
    result = await pool.fetchval('UPDATE workspace SET data=$1::jsonb,version=version+1 WHERE id=1 AND version=$2 RETURNING version',json.dumps(payload),version)
    if result is None: raise HTTPException(409,'Daten wurden zwischenzeitlich geändert. Bitte neu laden.')
    return {'version':result}

@app.post('/api/submissions')
async def submission(request: Request):
    # Stream the body: 1000 × 5 MiB must not allocate 5 GiB per pod.
    total = 0
    digest = hashlib.sha256()
    async for chunk in request.stream():
        total += len(chunk)
        if total>6*1024*1024: raise HTTPException(413,'Maximal 6 MiB.')
        digest.update(chunk)
    row_id = await pool.fetchval('INSERT INTO submissions(bytes,sha256) VALUES($1,$2) RETURNING id',total,digest.hexdigest())
    return {'id':row_id,'bytes':total,'sha256':digest.hexdigest()}

def make_pdf(data):
    buffer=io.BytesIO()
    styles=getSampleStyleSheet()
    doc=SimpleDocTemplate(buffer,pagesize=landscape(A4))
    elements=[Paragraph('Zendo – Projektbericht',styles['Title']),Spacer(1,15)]
    rows=[['Aufgabe','Status','Priorität','Verantwortlich','Fälligkeit']]
    for t in data:
        rows.append([Paragraph(escape(str(t.get(k,''))),styles['Normal']) for k in ['title','status','priority','assignee','due']])
    table=Table(rows,repeatRows=1,colWidths=[260,85,70,135,100])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eeeafd')),('GRID',(0,0),(-1,-1),.3,colors.lightgrey),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    elements.append(table);doc.build(elements)
    return buffer.getvalue()

@app.post('/api/reports/generate')
async def generate_report(request: Request):
    if report_slots.locked(): raise HTTPException(429,'Berichterstellung ausgelastet. Bitte erneut versuchen.',headers={'Retry-After':'3'})
    async with report_slots:
        try: options=json.loads(await body_limited(request,16384))
        except ValueError: raise HTTPException(422,'JSON erwartet.')
        await asyncio.sleep(max(1,float(os.getenv('REPORT_DELAY_SECONDS','2'))))
        row=await pool.fetchval('SELECT data FROM workspace WHERE id=1')
        tasks=json.loads(row)['tasks']
        tasks=[t for t in tasks if (options.get('project','all')=='all' or t['projectId']==options['project']) and (not options.get('from') or t.get('due','')>=options['from']) and (not options.get('to') or (t.get('due') and t['due']<=options['to']))]
        pdf=await asyncio.to_thread(make_pdf,tasks)
        return Response(pdf,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="zendo-bericht.pdf"'})
