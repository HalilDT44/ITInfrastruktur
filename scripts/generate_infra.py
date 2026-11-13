"""Render dependency-free Kubernetes JSON (JSON is valid YAML)."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
objects=[]
def labels(name,tier='ops'): return {'app.kubernetes.io/part-of':'zendo','app.kubernetes.io/name':name,'app.kubernetes.io/version':'1.0.0','tier':tier}
def obj(kind,name,spec=None,ns='zendo',api='v1',**extra):
    o={'apiVersion':api,'kind':kind,'metadata':{'name':name,'labels':labels(name)}}
    if ns:o['metadata']['namespace']=ns
    if spec is not None:o['spec']=spec
    o.update(extra);objects.append(o);return o
def cm(name,data,ns='zendo'):return obj('ConfigMap',name,ns=ns,data=data)
def volume(name,kind,ref):return {'name':name,kind:ref}
def mount(name,path,**kw):return {'name':name,'mountPath':path,**kw}
def secretfile(name,key):return {'name':name,'secret':{'secretName':key,'defaultMode':292}}
def env(name,value):return {'name':name,'value':str(value)}
def pvc(name,size,ns='zendo'):return obj('PersistentVolumeClaim',name,{'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':size}}},ns)
def probe(path,port):return {'httpGet':{'path':path,'port':port},'periodSeconds':10,'timeoutSeconds':5,'failureThreshold':3}
def workload(name,image,port,live,ready,ns='zendo',replicas=1,tier='ops',cpu='100m',memory='128Mi',limitcpu='500m',limitmem='256Mi',volumes=None,mounts=None,envs=None,args=None,command=None,uid=10001,readonly=True,kind='Deployment'):
    l=labels(name,tier)
    c={'name':name,'image':image,'imagePullPolicy':'IfNotPresent','ports':[{'containerPort':port,'name':'http'}], 'resources':{'requests':{'cpu':cpu,'memory':memory},'limits':{'cpu':limitcpu,'memory':limitmem}},'securityContext':{'runAsNonRoot':True,'runAsUser':uid,'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':readonly,'capabilities':{'drop':['ALL']}},'livenessProbe':live,'readinessProbe':ready}
    if envs:c['env']=envs
    if args:c['args']=args
    if command:c['command']=command
    c['volumeMounts']=(mounts or [])+[mount('tmp','/tmp')]
    pod={'enableServiceLinks':False,'automountServiceAccountToken':False,'terminationGracePeriodSeconds':75,'securityContext':{'fsGroup':uid},'containers':[c],'volumes':(volumes or [])+[{'name':'tmp','emptyDir':{}}]}
    spec={'replicas':replicas,'selector':{'matchLabels':{'app.kubernetes.io/name':name}},'template':{'metadata':{'labels':l},'spec':pod}}
    if kind=='Deployment':spec.update(strategy={'type':'RollingUpdate','rollingUpdate':{'maxUnavailable':0,'maxSurge':1}},minReadySeconds=5)
    else:spec['serviceName']=name
    o=obj(kind,name,spec,ns,api='apps/v1');o['metadata']['labels']=l
    obj('Service',name,{'selector':{'app.kubernetes.io/name':name},'ports':[{'name':'http','port':port,'targetPort':port}]},ns)
    return pod,c

for ns in ['zendo','monitoring']:obj('Namespace',ns,ns=None)
cm('app-config',{'DB_HOST':'db','DB_POOL_SIZE':'10','REPORT_DELAY_SECONDS':'2','REPORT_CONCURRENCY':'16'})
cm('web-config',{'default.conf':(ROOT/'nginx.conf').read_text()})
pvc('db-data','5Gi');pvc('backups','5Gi')
dbprobe={'exec':{'command':['sh','-c','pg_isready -U zendo -d zendo']},'periodSeconds':10,'timeoutSeconds':5}
dbready={'exec':{'command':['sh','-c','PGPASSWORD="$(cat /run/secrets/db_password)" psql -h 127.0.0.1 -U zendo -d zendo -tAc "SELECT 1"']},'periodSeconds':10,'timeoutSeconds':5}
pod,c=workload('db','postgres:17-alpine',5432,dbprobe,dbready,tier='data',uid=70,cpu='250m',memory='256Mi',limitcpu='2',limitmem='1Gi',kind='StatefulSet',volumes=[volume('data','persistentVolumeClaim',{'claimName':'db-data'}),secretfile('password','db-secret'),{'name':'run','emptyDir':{}}],mounts=[mount('data','/var/lib/postgresql/data'),mount('password','/run/secrets',readOnly=True),mount('run','/var/run/postgresql')],envs=[env('POSTGRES_USER','zendo'),env('POSTGRES_DB','zendo'),env('POSTGRES_PASSWORD_FILE','/run/secrets/db_password'),env('PGDATA','/var/lib/postgresql/data/pgdata')])
pod,c=workload('api','zendo-api:1.0.0',8000,probe('/api/live',8000),probe('/api/ready',8000),replicas=2,tier='backend',cpu='250m',memory='192Mi',limitcpu='2',limitmem='512Mi',volumes=[secretfile('password','db-secret')],mounts=[mount('password','/run/secrets',readOnly=True)])
c['envFrom']=[{'configMapRef':{'name':'app-config'}}]
pod['containers'][0]['lifecycle']={'preStop':{'exec':{'command':['python','-c','import time; time.sleep(10)']}}}
pod['containers'][0]['startupProbe']={**probe('/api/live',8000),'failureThreshold':30}
pod['topologySpreadConstraints']=[{'maxSkew':1,'topologyKey':'kubernetes.io/hostname','whenUnsatisfiable':'ScheduleAnyway','labelSelector':{'matchLabels':{'app.kubernetes.io/name':'api'}}}]
pod,c=workload('web','zendo-web:1.0.0',8080,probe('/health',8080),probe('/ready',8080),replicas=2,tier='frontend',uid=101,volumes=[volume('config','configMap',{'name':'web-config'})],mounts=[mount('config','/etc/nginx/conf.d',readOnly=True)])
pod['containers'][0]['lifecycle']={'preStop':{'exec':{'command':['sh','-c','sleep 10; nginx -s quit']}}}
cm('waf-config',{'REQUEST-900-EXCLUSION-RULES-BEFORE-CRS.conf':'SecRule REQUEST_URI "@streq /api/submissions" "id:1001,phase:1,pass,nolog,ctl:requestBodyAccess=Off"\n','proxy_backend.conf.template':'proxy_http_version 1.1;\nproxy_set_header Host $host;\nproxy_set_header Connection "";\nproxy_request_buffering off;\nproxy_buffering off;\nproxy_connect_timeout 10s;\nproxy_send_timeout 300s;\nproxy_read_timeout 300s;\nproxy_pass http://web:8080;\n'})
pod,c=workload('waf','owasp/modsecurity-crs:nginx',8080,{'tcpSocket':{'port':8080},'periodSeconds':10},probe('/ready',8080),replicas=2,tier='edge',uid=101,readonly=False,cpu='200m',memory='256Mi',limitcpu='2',limitmem='1Gi',envs=[env('CLIENT_BODY_TIMEOUT','300s'),env('ALLOWED_METHODS','GET HEAD POST OPTIONS PUT'),env('ALLOWED_REQUEST_CONTENT_TYPE','|application/json| |application/octet-stream|'),env('BACKEND','http://web:8080'),env('PORT',8080),env('MODSEC_RULE_ENGINE','On'),env('MODSEC_REQ_BODY_LIMIT',6291456),env('MODSEC_REQ_BODY_NOFILES_LIMIT',6291456),env('MODSEC_REQ_BODY_LIMIT_ACTION','Reject')])
pod['volumes'].append(volume('wafconfig','configMap',{'name':'waf-config'}))
c['volumeMounts'] += [mount('wafconfig','/etc/modsecurity.d/owasp-crs/rules/REQUEST-900-EXCLUSION-RULES-BEFORE-CRS.conf',subPath='REQUEST-900-EXCLUSION-RULES-BEFORE-CRS.conf',readOnly=True),mount('wafconfig','/etc/nginx/templates/includes/proxy_backend.conf.template',subPath='proxy_backend.conf.template',readOnly=True)]
for name in ['api','web','waf']:
    obj('PodDisruptionBudget',name,{'minAvailable':1,'selector':{'matchLabels':{'app.kubernetes.io/name':name}}},api='policy/v1')
    obj('HorizontalPodAutoscaler',name,{'scaleTargetRef':{'apiVersion':'apps/v1','kind':'Deployment','name':name},'minReplicas':2,'maxReplicas':8,'metrics':[{'type':'Resource','resource':{'name':'cpu','target':{'type':'Utilization','averageUtilization':65}}}],'behavior':{'scaleDown':{'stabilizationWindowSeconds':180}}},api='autoscaling/v2')
obj('Ingress','zendo',{'ingressClassName':'traefik','tls':[{'hosts':['zendo.local'],'secretName':'zendo-tls'}],'rules':[{'host':'zendo.local','http':{'paths':[{'path':'/','pathType':'Prefix','backend':{'service':{'name':'waf','port':{'number':8080}}}}]}}]},api='networking.k8s.io/v1')['metadata']['annotations']={'traefik.ingress.kubernetes.io/router.entrypoints':'websecure','traefik.ingress.kubernetes.io/router.tls':'true'}
# Default-deny ingress plus explicit paths; DNS/egress separately constrained for application pods.
for ns in ['zendo','monitoring']:
    obj('NetworkPolicy','default-deny',{'podSelector':{},'policyTypes':['Ingress']},ns,api='networking.k8s.io/v1')
def allow(name,target,sources,ports,ns='zendo'):
    obj('NetworkPolicy',name,{'podSelector':{'matchLabels':{'app.kubernetes.io/name':target}},'policyTypes':['Ingress'],'ingress':[{'from':sources,'ports':[{'protocol':'TCP','port':p} for p in ports]}]},ns,api='networking.k8s.io/v1')
def source(name,ns=None):
    x={'podSelector':{'matchLabels':{'app.kubernetes.io/name':name}}}
    if ns:x['namespaceSelector']={'matchLabels':{'kubernetes.io/metadata.name':ns}}
    return x
allow('ingress-waf','waf',[source('traefik','kube-system')],[8080])
allow('waf-web','web',[source('waf')],[8080])
allow('web-api','api',[source('web'),source('prometheus','monitoring')],[8000])
allow('api-db','db',[source('api'),source('backup')],[5432])
for name,peers,ports in [('waf',['web'],[8080]),('web',['api'],[8000]),('api',['db'],[5432]),('db',[],[]),('backup',['db'],[5432])]:
    egress=[{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}}}],'ports':[{'protocol':'UDP','port':53},{'protocol':'TCP','port':53}]}]
    if peers:egress.append({'to':[source(p) for p in peers],'ports':[{'protocol':'TCP','port':p} for p in ports]})
    obj('NetworkPolicy',name+'-egress',{'podSelector':{'matchLabels':{'app.kubernetes.io/name':name}},'policyTypes':['Egress'],'egress':egress},api='networking.k8s.io/v1')
backup={'schedule':'0 */6 * * *','concurrencyPolicy':'Forbid','successfulJobsHistoryLimit':2,'failedJobsHistoryLimit':3,'jobTemplate':{'spec':{'template':{'metadata':{'labels':labels('backup','data')},'spec':{'restartPolicy':'OnFailure','automountServiceAccountToken':False,'securityContext':{'runAsUser':70,'runAsNonRoot':True,'fsGroup':70},'containers':[{'name':'backup','image':'postgres:17-alpine','command':['sh','-ec','export PGPASSWORD="$(cat /run/secrets/db_password)"; file=/backups/zendo-$(date -u +%Y%m%dT%H%M%SZ).dump; pg_dump -h db -U zendo -d zendo -Fc -f "$file.tmp"; mv "$file.tmp" "$file"; find /backups -name "*.dump" -mtime +7 -delete'],'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}},'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},'volumeMounts':[mount('backup','/backups'),mount('password','/run/secrets',readOnly=True)]}],'volumes':[volume('backup','persistentVolumeClaim',{'claimName':'backups'}),secretfile('password','db-secret')]}}}}}
obj('CronJob','backup',backup,api='batch/v1')

# Monitoring: all servers are Deployments, with state on PVCs.
for name in ['prometheus','grafana','alertmanager']:pvc(name+'-data','2Gi','monitoring')
obj('ServiceAccount','prometheus',ns='monitoring')
obj('ClusterRole','zendo-monitoring',ns=None,api='rbac.authorization.k8s.io/v1',rules=[{'apiGroups':[''],'resources':['nodes','nodes/proxy','services','endpoints','pods'],'verbs':['get','list','watch']},{'nonResourceURLs':['/metrics','/metrics/cadvisor'],'verbs':['get']}])
obj('ClusterRoleBinding','zendo-monitoring',ns=None,api='rbac.authorization.k8s.io/v1',roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'ClusterRole','name':'zendo-monitoring'},subjects=[{'kind':'ServiceAccount','name':'prometheus','namespace':'monitoring'}])
prom={'global':{'scrape_interval':'15s','evaluation_interval':'15s'},'rule_files':['/etc/prometheus/rules.json'],'alerting':{'alertmanagers':[{'static_configs':[{'targets':['alertmanager:9093']}]}]},'scrape_configs':[
 {'job_name':'api','kubernetes_sd_configs':[{'role':'pod','namespaces':{'names':['zendo']}}],'relabel_configs':[{'source_labels':['__meta_kubernetes_pod_label_app_kubernetes_io_name'],'regex':'api','action':'keep'},{'source_labels':['__meta_kubernetes_pod_container_port_number'],'regex':'8000','action':'keep'},{'source_labels':['__meta_kubernetes_pod_name'],'target_label':'pod'}]},
 {'job_name':'kube-state-metrics','static_configs':[{'targets':['kube-state-metrics:8080']}]},
 {'job_name':'cadvisor','scheme':'https','authorization':{'credentials_file':'/var/run/secrets/kubernetes.io/serviceaccount/token'},'tls_config':{'ca_file':'/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'},'kubernetes_sd_configs':[{'role':'node'}],'relabel_configs':[{'target_label':'__address__','replacement':'kubernetes.default.svc:443'},{'source_labels':['__meta_kubernetes_node_name'],'target_label':'__metrics_path__','replacement':'/api/v1/nodes/$1/proxy/metrics/cadvisor'}]},
 {'job_name':'traefik','kubernetes_sd_configs':[{'role':'pod','namespaces':{'names':['kube-system']}}],'relabel_configs':[{'source_labels':['__meta_kubernetes_pod_label_app_kubernetes_io_name'],'regex':'traefik','action':'keep'},{'source_labels':['__meta_kubernetes_pod_container_port_name'],'regex':'metrics','action':'keep'}]}
]}
rules=[]
for name,expr,duration,severity in [
 ('BackendUnavailable','sum(up{job="api"}) == 0 or absent(up{job="api"})','30s','critical'),
 ('DatabaseUnavailable','min(zendo_database_up) == 0 or kube_statefulset_status_replicas_ready{namespace="zendo",statefulset="db"} == 0','30s','critical'),
 ('PodNotReady','kube_pod_status_ready{namespace=~"zendo|monitoring",condition="true"} == 0','1m','warning'),
 ('ContainerRestart','increase(kube_pod_container_status_restarts_total{namespace=~"zendo|monitoring"}[5m]) > 0','0s','warning'),
 ('ReplicasMissing','kube_deployment_status_replicas_available{namespace=~"zendo|monitoring"} < kube_deployment_spec_replicas{namespace=~"zendo|monitoring"}','1m','critical'),
 ('ContainerMemoryLimit','container_memory_working_set_bytes{namespace=~"zendo|monitoring",container!=""} / on(namespace,pod,container) group_left kube_pod_container_resource_limits{resource="memory",namespace=~"zendo|monitoring"} > 0.9','1m','warning'),
 ('MemoryHigh','container_memory_working_set_bytes{namespace="zendo",container="api"} > 450000000','2m','warning'),
 ('CPUHigh','sum by(pod)(rate(container_cpu_usage_seconds_total{namespace="zendo",container="api"}[2m])) > 1.4','2m','warning'),
 ('ReportSlow','histogram_quantile(0.95,sum by(le)(rate(zendo_request_seconds_bucket{route="/api/reports/generate"}[5m]))) > 5','2m','warning'),
 ('BackupFailed','kube_job_status_failed{namespace="zendo"} > 0','1m','critical'),
 ('IngressErrors','sum(rate(traefik_service_requests_total{code=~"5.."}[5m])) / clamp_min(sum(rate(traefik_service_requests_total[5m])),1) > 0.05','1m','critical')]:rules.append({'alert':name,'expr':expr,'for':duration,'labels':{'severity':severity},'annotations':{'summary':name+' – Zendo Infrastruktur prüfen'}})
cm('prometheus-config',{'prometheus.json':json.dumps(prom),'rules.json':json.dumps({'groups':[{'name':'zendo','rules':rules}]})},'monitoring')
pod,c=workload('prometheus','prom/prometheus:v3.7.3',9090,probe('/-/healthy',9090),probe('/-/ready',9090),ns='monitoring',uid=65534,memory='256Mi',limitmem='1Gi',volumes=[volume('config','configMap',{'name':'prometheus-config'}),volume('data','persistentVolumeClaim',{'claimName':'prometheus-data'})],mounts=[mount('config','/etc/prometheus'),mount('data','/prometheus')],args=['--config.file=/etc/prometheus/prometheus.json','--storage.tsdb.path=/prometheus','--storage.tsdb.retention.time=7d'])
pod['automountServiceAccountToken']=True;pod['serviceAccountName']='prometheus';objects[-2]['spec']['strategy']={'type':'Recreate'}
cm('grafana-config',{'datasources.yaml':json.dumps({'apiVersion':1,'datasources':[{'name':'Prometheus','type':'prometheus','uid':'prometheus','access':'proxy','url':'http://prometheus:9090','isDefault':True}]}),'dashboards.yaml':json.dumps({'apiVersion':1,'providers':[{'name':'Zendo','folder':'Zendo','type':'file','options':{'path':'/var/lib/grafana/dashboards'}}]})},'monitoring')
queries=[('CPU je Pod','sum by(pod)(rate(container_cpu_usage_seconds_total{namespace="zendo"}[2m]))'),('Speicher je Pod','sum by(pod)(container_memory_working_set_bytes{namespace="zendo"})'),('Verfügbare Replicas','kube_deployment_status_replicas_available{namespace="zendo"}'),('Gewünschte Replicas','kube_deployment_spec_replicas{namespace="zendo"}'),('Pod Ready','kube_pod_status_ready{namespace="zendo",condition="true"}'),('API Rate','sum(rate(zendo_requests_total[1m]))'),('API p95','histogram_quantile(.95,sum by(le)(rate(zendo_request_seconds_bucket[2m])))'),('Ingress Rate','sum(rate(traefik_service_requests_total[1m]))'),('Ingress p95','histogram_quantile(.95,sum by(le)(rate(traefik_service_request_duration_seconds_bucket[2m])))'),('Datenbank','zendo_database_up'),('Container Neustarts','kube_pod_container_status_restarts_total{namespace="zendo"}')]
dashboard={'title':'Zendo Infrastruktur','uid':'zendo','schemaVersion':39,'version':1,'refresh':'10s','panels':[{'id':i+1,'title':title,'type':'timeseries','datasource':{'type':'prometheus','uid':'prometheus'},'gridPos':{'x':(i%2)*12,'y':(i//2)*8,'w':12,'h':8},'targets':[{'expr':query,'refId':'A'}]} for i,(title,query) in enumerate(queries)]}
cm('grafana-dashboard',{'zendo.json':json.dumps(dashboard)},'monitoring')
pod,c=workload('grafana','grafana/grafana:12.2.1',3000,{'tcpSocket':{'port':3000},'periodSeconds':10},probe('/api/health',3000),ns='monitoring',uid=472,memory='128Mi',limitmem='512Mi',volumes=[volume('data','persistentVolumeClaim',{'claimName':'grafana-data'}),volume('config','configMap',{'name':'grafana-config'}),volume('dashboard','configMap',{'name':'grafana-dashboard'}),secretfile('password','grafana-secret')],mounts=[mount('data','/var/lib/grafana'),mount('config','/etc/grafana/provisioning/datasources/datasources.yaml',subPath='datasources.yaml'),mount('config','/etc/grafana/provisioning/dashboards/dashboards.yaml',subPath='dashboards.yaml'),mount('dashboard','/var/lib/grafana/dashboards'),mount('password','/run/secrets',readOnly=True)],envs=[env('GF_SECURITY_ADMIN_PASSWORD__FILE','/run/secrets/admin_password'),env('GF_USERS_ALLOW_SIGN_UP','false')])
objects[-2]['spec']['strategy']={'type':'Recreate'}
pod,c=workload('alertmanager','prom/alertmanager:v0.28.1',9093,probe('/-/healthy',9093),probe('/-/ready',9093),ns='monitoring',uid=65534,volumes=[secretfile('config','alertmanager-secret'),volume('data','persistentVolumeClaim',{'claimName':'alertmanager-data'})],mounts=[mount('config','/etc/alertmanager'),mount('data','/alertmanager')],args=['--config.file=/etc/alertmanager/alertmanager.json','--storage.path=/alertmanager','--cluster.listen-address='])
objects[-2]['spec']['strategy']={'type':'Recreate'}
cm('notifier-code',{'notify.py':(ROOT/'backend/notify.py').read_text()},'monitoring')
pod,c=workload('notifier','zendo-api:1.0.0',8080,probe('/live',8080),probe('/ready',8080),ns='monitoring',command=['python','/code/notify.py'],volumes=[volume('code','configMap',{'name':'notifier-code'})],mounts=[mount('code','/code')])
obj('ServiceAccount','kube-state-metrics',ns='monitoring')
obj('ClusterRole','zendo-state-metrics',ns=None,api='rbac.authorization.k8s.io/v1',rules=[{'apiGroups':[''],'resources':['pods','nodes','persistentvolumeclaims'],'verbs':['list','watch']},{'apiGroups':['apps'],'resources':['deployments','statefulsets','replicasets'],'verbs':['list','watch']},{'apiGroups':['batch'],'resources':['jobs','cronjobs'],'verbs':['list','watch']}])
obj('ClusterRoleBinding','zendo-state-metrics',ns=None,api='rbac.authorization.k8s.io/v1',roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'ClusterRole','name':'zendo-state-metrics'},subjects=[{'kind':'ServiceAccount','name':'kube-state-metrics','namespace':'monitoring'}])
pod,c=workload('kube-state-metrics','registry.k8s.io/kube-state-metrics/kube-state-metrics:v2.17.0',8080,probe('/healthz',8080),probe('/readyz',8081),ns='monitoring',uid=65534,args=['--resources=pods,nodes,persistentvolumeclaims,deployments,statefulsets,replicasets,jobs,cronjobs'])
pod['automountServiceAccountToken']=True;pod['serviceAccountName']='kube-state-metrics'
for name,port,froms in [('prometheus',9090,['grafana']),('alertmanager',9093,['prometheus']),('notifier',8080,['alertmanager']),('kube-state-metrics',8080,['prometheus'])]:allow('allow-'+name,name,[source(s) for s in froms],[port],'monitoring')
# kubectl port-forward accesses pod sockets directly, no public monitoring ingress.
ROOT.joinpath('k8s').mkdir(exist_ok=True)
ROOT.joinpath('k8s/stack.yaml').write_text(json.dumps({'apiVersion':'v1','kind':'List','items':objects},indent=2)+'\n')
print(f'{len(objects)} Ressourcen nach k8s/stack.yaml geschrieben')

