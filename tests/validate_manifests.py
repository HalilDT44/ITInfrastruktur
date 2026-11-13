import json
from pathlib import Path
x=json.loads(Path('k8s/stack.yaml').read_text())['items']
assert all(o['metadata'].get('labels',{}).get('app.kubernetes.io/part-of')=='zendo' for o in x)
for o in x:
    if o['kind'] not in ['Deployment','StatefulSet','CronJob']:continue
    pod=o['spec']['jobTemplate']['spec']['template']['spec'] if o['kind']=='CronJob' else o['spec']['template']['spec']
    for c in pod['containers']:
        assert c['resources']['requests'] and c['resources']['limits'],o['metadata']['name']
        assert c['securityContext'].get('runAsNonRoot',pod.get('securityContext',{}).get('runAsNonRoot')),o['metadata']['name']
        if o['kind']!='CronJob':assert c['livenessProbe']!=c['readinessProbe'],o['metadata']['name']
assert len([o for o in x if o['kind']=='NetworkPolicy'])>=10
assert all(o['spec']['replicas']>=2 for o in x if o['kind']=='Deployment' and o['metadata']['namespace']=='zendo')
print('PASS: Labels, Requests/Limits, Non-Root, distinct probes, NetworkPolicies, replicas.')
