"""Backup restore and negative NetworkPolicy checks in the isolated lab."""
import json, subprocess
from pathlib import Path
def k(*args,**kw):return subprocess.run(['kubectl',*args],check=True,text=True,**kw)
ctx=subprocess.check_output(['kubectl','config','current-context'],text=True).strip()
if ctx!='k3d-zendo-validation':raise SystemExit('Only the isolated validation cluster is supported.')
def job(name,image,command,labels,uid=10001,volumes=[],mounts=[]):
    data={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':'zendo'},'spec':{'backoffLimit':0,'template':{'metadata':{'labels':labels},'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':uid,'fsGroup':uid},'containers':[{'name':'check','image':image,'command':command,'securityContext':{'readOnlyRootFilesystem':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}},'volumeMounts':mounts}],'volumes':volumes}}}}
    k('-n','zendo','delete','job',name,'--ignore-not-found');k('apply','-f','-',input=json.dumps(data));k('-n','zendo','wait','--for=condition=complete','job/'+name,'--timeout=180s')
    result=subprocess.check_output(['kubectl','-n','zendo','logs','job/'+name],text=True)
    Path('artifacts/'+name+'.log').write_text(result);print(name+': '+result)
job('network-denial-validation','zendo-api:1.0.0',['python','-c',"import socket,sys\ntry: socket.create_connection(('db',5432),3)\nexcept (TimeoutError,OSError): print('PASS: unauthorized DB access denied');sys.exit(0)\nraise SystemExit('FAIL: database accessible')"],{'app.kubernetes.io/name':'untrusted-test'})
job('restore-validation','postgres:17-alpine',['sh','-ec','export PGPASSWORD="$(cat /run/secrets/db_password)"; until pg_isready -h db -U zendo; do sleep 2; done; file=$(ls /backups/*.dump | tail -1); test -n "$file"; createdb -h db -U zendo zendo_restore_validation; trap "dropdb -h db -U zendo zendo_restore_validation" EXIT; pg_restore -h db -U zendo -d zendo_restore_validation --no-owner "$file"; psql -h db -U zendo -d zendo_restore_validation -c "SELECT count(*) FROM workspace"; echo "PASS: pg_dump restored into separate validation database"'],{'app.kubernetes.io/name':'backup'},70,[{'name':'backups','persistentVolumeClaim':{'claimName':'backups'}},{'name':'password','secret':{'secretName':'db-secret'}}],[{'name':'backups','mountPath':'/backups','readOnly':True},{'name':'password','mountPath':'/run/secrets','readOnly':True}])
