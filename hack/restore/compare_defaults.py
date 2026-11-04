"""Explain only explicit Kubernetes v1.33 additions; never erase source fields.

This fixture policy is intentionally narrow. Unknown additions, removed fields,
changed source values, reordered lists, and unexpected default values fail.
Raw differences are retained beside the classified result.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re

from music_e2e import differences, save

SPEC_DEFAULTS = {
 'Namespace': {'spec': {'finalizers':['kubernetes']}},
 'Deployment': {'spec/progressDeadlineSeconds':600,'spec/revisionHistoryLimit':10,
   'spec/strategy':{'rollingUpdate':{'maxSurge':'25%','maxUnavailable':'25%'},'type':'RollingUpdate'}},
 'StatefulSet': {'spec/persistentVolumeClaimRetentionPolicy':{'whenDeleted':'Retain','whenScaled':'Retain'},
   'spec/podManagementPolicy':'OrderedReady','spec/revisionHistoryLimit':10,
   'spec/updateStrategy':{'rollingUpdate':{'partition':0},'type':'RollingUpdate'}},
 'CronJob': {'spec/concurrencyPolicy':'Allow','spec/failedJobsHistoryLimit':1,
   'spec/successfulJobsHistoryLimit':3,'spec/suspend':False,
   'spec/jobTemplate/metadata':{'creationTimestamp':None},
   'spec/jobTemplate/spec/template/metadata':{}},
 'Service': {'spec/internalTrafficPolicy':'Cluster','spec/ipFamilies':['IPv4'],
   'spec/ipFamilyPolicy':'SingleStack','spec/sessionAffinity':'None','spec/type':'ClusterIP'},
}
POD_DEFAULTS={'dnsPolicy':'ClusterFirst','restartPolicy':'Always','schedulerName':'default-scheduler',
              'securityContext':{},'terminationGracePeriodSeconds':30}
CONTAINER_DEFAULTS={'imagePullPolicy':'IfNotPresent','resources':{},
 'terminationMessagePath':'/dev/termination-log','terminationMessagePolicy':'File',
 'readinessProbe/failureThreshold':3,'readinessProbe/httpGet/scheme':'HTTP',
 'readinessProbe/periodSeconds':10,'readinessProbe/successThreshold':1,'readinessProbe/timeoutSeconds':1}


def explanation(kind, diff):
    if diff['change']!='added':return None
    path=diff['path'].lstrip('/');value=diff['actual']
    if path in SPEC_DEFAULTS.get(kind,{}) and value==SPEC_DEFAULTS[kind][path]:
        return 'Kubernetes API default/bookkeeping'
    if kind=='Node' and re.fullmatch(r'spec/taints/\d+',path) and value=={
        'key':'node.kubernetes.io/not-ready','effect':'NoSchedule'}:
        return 'API-added not-ready taint on a synthetic Node without a kubelet'
    if kind=='Service':
        if re.fullmatch(r'spec/ports/\d+/protocol',path) and value=='TCP':return 'Service protocol default'
        if path in ('spec/clusterIP','spec/clusterIPs'):
            addresses=value if isinstance(value,list) else [value]
            if addresses and all(isinstance(v,str) and ipaddress.ip_address(v) in ipaddress.ip_network('10.0.0.0/24') for v in addresses):
                return 'Fresh isolated API Service address allocation (not original state)'
    prefix=('spec/jobTemplate/spec/template/spec/' if kind=='CronJob' else 'spec/template/spec/')
    if kind in ('Deployment','StatefulSet','CronJob') and path.startswith(prefix):
        sub=path[len(prefix):]
        if sub in POD_DEFAULTS and value==POD_DEFAULTS[sub]:return 'PodSpec API default'
        match=re.fullmatch(r'containers/\d+/(.+)',sub)
        if match:
            sub=match[1]
            if sub in CONTAINER_DEFAULTS and value==CONTAINER_DEFAULTS[sub]:return 'Container/probe API default'
            if re.fullmatch(r'ports/\d+/protocol',sub) and value=='TCP':return 'Container port protocol default'
    return None


def classify(source):
    result=json.loads(json.dumps(source));exact=0;unexplained=[]
    for row in result['objects']:
        expanded=[]
        for d in row['differences']:
            expanded.extend(differences(d['expected'],d['actual'],d['path']) if d['change']=='changed' else [d])
        row['differences']=expanded
        for d in expanded:
            d['explanation']=explanation(row['identity'][1],d)
            if not d['explanation']:unexplained.append({'identity':row['identity'],**d})
        row['exact_ignoring_explained_server_additions']=all(d['explanation'] for d in expanded)
        exact+=row['exact_ignoring_explained_server_additions']
    result['exact_ignoring_explained_server_additions']=exact
    result['unexplained']=unexplained
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('comparison',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=classify(json.loads(a.comparison.read_text()));save(a.out,result)
    print(json.dumps({k:v for k,v in result.items() if k!='objects'}))
    if result['unexplained']:raise SystemExit(1)


if __name__=='__main__':main()
