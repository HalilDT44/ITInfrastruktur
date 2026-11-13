"""Create local secrets; optionally deploy to the explicitly selected kubectl context."""
import argparse, base64, json, os, secrets, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def run(args,**kw):return subprocess.run(args,check=True,cwd=ROOT,**kw)
def apply(o):run(['kubectl','apply','-f','-'],input=json.dumps(o),text=True)
def secret(name,ns,data,kind='Opaque'):
    apply({'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':ns,'labels':{'app.kubernetes.io/part-of':'zendo','app.kubernetes.io/name':name,'app.kubernetes.io/version':'1.0.0','tier':'config'}},'type':kind,'data':{k:base64.b64encode(v.encode() if isinstance(v,str) else v).decode() for k,v in data.items()}})

parser=argparse.ArgumentParser()
parser.add_argument('--kubernetes',action='store_true')
parser.add_argument('--domain',default='zendo.local')
parser.add_argument('--registry',help='e.g. ghcr.io/group (images must already be pushed)')
parser.add_argument('--webhook',help='Optional external Alertmanager-compatible webhook receiver')
parser.add_argument('--local-k3d',help='Explicit k3d cluster name for image import')
parser.add_argument('--configure-traefik',action='store_true',help='Apply k3s HelmChartConfig for 300s upload timeouts')
args=parser.parse_args()
directory=ROOT/'.secrets';directory.mkdir(exist_ok=True)
for filename in ['db_password','admin_password']:
    p=directory/filename
    if not p.exists():p.write_text(secrets.token_urlsafe(32));os.chmod(p,0o600)
if not args.kubernetes:
    print('Lokale Secrets bereit. Start: docker compose up -d --build');raise SystemExit()
run(['kubectl','config','current-context'])
if args.configure_traefik or args.local_k3d:run(['kubectl','apply','-f','infrastructure/traefik-k3s.yaml'])
run(['python',str(ROOT/'scripts/generate_infra.py')])
stack=json.loads((ROOT/'k8s/stack.yaml').read_text())
for ns in ['zendo','monitoring']:apply({'apiVersion':'v1','kind':'Namespace','metadata':{'name':ns,'labels':{'app.kubernetes.io/part-of':'zendo'}}})
secret('db-secret','zendo',{'db_password':(directory/'db_password').read_text()})
secret('grafana-secret','monitoring',{'admin_password':(directory/'admin_password').read_text()})
alertconfig={'route':{'receiver':'notifications','group_by':['alertname'],'group_wait':'10s','group_interval':'30s','repeat_interval':'1h'},'receivers':[{'name':'notifications','webhook_configs':[{'url':args.webhook or 'http://notifier:8080/alerts','send_resolved':True}]}]}
secret('alertmanager-secret','monitoring',{'alertmanager.json':json.dumps(alertconfig)})
# OpenSSL runs in a disposable container; private keys never enter an image.
certdir=directory/('tls-'+args.domain);certdir.mkdir(exist_ok=True)
if not (certdir/'tls.crt').exists():
    run(['docker','run','--rm','-v',f'{certdir}:/certs','alpine/openssl','req','-x509','-nodes','-newkey','rsa:3072','-days','365','-keyout','/certs/tls.key','-out','/certs/tls.crt','-subj',f'/CN={args.domain}','-addext',f'subjectAltName=DNS:{args.domain}'])
secret('zendo-tls','zendo',{'tls.crt':(certdir/'tls.crt').read_bytes(),'tls.key':(certdir/'tls.key').read_bytes()},'kubernetes.io/tls')
if args.local_k3d:
    run(['docker','exec',f'k3d-{args.local_k3d}-serverlb','sh','-ec',"sed -i 's@worker_connections .*;@worker_connections 8192;@' /etc/confd/templates/nginx.tmpl /etc/nginx/nginx.conf; nginx -t; nginx -s reload"])
    for name,context in [('web','.'),('api','backend')]:run(['docker','build','-t',f'zendo-{name}:1.0.0',context])
    run(['k3d','image','import','zendo-web:1.0.0','zendo-api:1.0.0','-c',args.local_k3d])
for o in stack['items']:
    if o['kind']=='Ingress':
        o['spec']['rules'][0]['host']=args.domain;o['spec']['tls'][0]['hosts']=[args.domain]
    if args.registry and o['kind']=='Deployment':
        for c in o['spec']['template']['spec']['containers']:
            if c['image'].startswith('zendo-'):c['image']=args.registry.rstrip('/')+'/'+c['image']
apply(stack)
for name in ['api','web','waf']:run(['kubectl','-n','zendo','rollout','status','deployment/'+name,'--timeout=300s'])
print(f'Anwendung: https://{args.domain} | Health: https://{args.domain}/api/health')
