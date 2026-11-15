"""kopf controller. One immutable Job identity per atelier/night, no automatic retry."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import kopf
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from mnemosyne.operator.kube import connect
from mnemosyne.operator.policy import job_name, window


@kopf.on.startup()
def startup(settings, **_):
    settings.posting.enabled = False
    # One namespace, one known resource: no cluster-wide CRD or namespace scans, so a tenant
    # install needs no cluster role (found on the first real install: 403 on both lists).
    settings.scanning.disabled = True
    settings.persistence.progress_storage = kopf.StatusProgressStorage(field='status.kopf.progress')
    settings.persistence.diffbase_storage = kopf.AnnotationsDiffBaseStorage(prefix='mnemosyne.art')


def idle_cluster(api):
    """Portable conservative idle signal: no pressure, pending pods, or busy CPU.

    Metrics API is optional on conformance clusters: absence means not idle.
    """
    from kubernetes.utils.quantity import parse_quantity
    core = client.CoreV1Api(api)
    nodes = core.list_node().items
    if not nodes or any(c.status == 'True' and c.type.endswith('Pressure')
                        for n in nodes for c in n.status.conditions):
        return False
    if any(p.status.phase == 'Pending' for p in core.list_pod_for_all_namespaces().items):
        return False
    try:
        metrics = client.CustomObjectsApi(api).list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'nodes')
    except ApiException:
        return False
    capacities = {n.metadata.name: parse_quantity(n.status.allocatable['cpu']) for n in nodes}
    return (len(metrics['items']) == len(nodes) and all(
        parse_quantity(n['usage']['cpu']) < capacities[n['metadata']['name']] / 5
        for n in metrics['items']))


def make_job(body, runtime, night, seconds):
    name = job_name(body['metadata']['uid'], night)
    spec = body['spec']['runtime']
    pod = copy.deepcopy(runtime['pod'])
    container = pod['containers'][0]
    container.setdefault('env', []).extend([
        {'name': 'MNEMO_ATELIER', 'value': body['metadata']['name']},
        {'name': 'MNEMO_NIGHT', 'value': night},
        {'name': 'MNEMO_REQUEST', 'value': json.dumps(spec, separators=(',', ':'))},
    ])
    # Job-specific request is passed as data, never interpolated into a shell.
    pod['restartPolicy'] = 'Never'
    return {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {
        'name': name, 'namespace': body['metadata']['namespace'],
        'labels': {'mnemosyne.art/atelier': body['metadata']['name']}},
        'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': min(seconds, spec.get('deadlineSeconds', 21600)),
                 'template': {'metadata': {'labels': {'mnemosyne.art/job': name}}, 'spec': pod}}}


@kopf.timer('mnemosyne.art', 'v1alpha1', 'ateliers', interval=30)
def reconcile(body, patch, **_):
    spec = body.get('spec', {}).get('runtime')
    if not spec:
        return
    runtime = json.loads(Path(os.environ['MNEMO_RUNTIME']).read_text())
    with connect() as api:
        batch = client.BatchV1Api(api)
        namespace = body['metadata']['namespace']
        jobs = batch.list_namespaced_job(namespace,
            label_selector='mnemosyne.art/atelier=' + body['metadata']['name']).items
        active = [j for j in jobs if not (j.status.succeeded or j.status.failed)]
        if spec.get('suspend', False):
            for job in active:
                if not job.spec.suspend:
                    batch.patch_namespaced_job(job.metadata.name, namespace, {'spec': {'suspend': True}})
            patch.status['phase'] = 'Suspended'
            return
        policy = spec.get('window', {})
        if policy.get('kind') == 'continuous':
            # Life without pause: each finished day of the atelier's life is followed by the next.
            if active:
                patch.status['phase'] = 'Running'
                return
            step = int((body.get('status') or {}).get('step', 0))
            name = job_name(body['metadata']['uid'], f'step-{step}')
            existing = next((j for j in jobs if j.metadata.name == name), None)
            if existing:
                done = existing.status.completion_time or (existing.status.conditions or [None])[-1]
                finished = getattr(done, 'last_transition_time', done)
                # A failed day is recorded and life goes on, after a pause so a broken day does not spin.
                if existing.status.failed and finished and \
                        (datetime.now(timezone.utc) - finished).total_seconds() < 600:
                    patch.status['phase'] = 'Failed'
                    return
                patch.status['step'] = step + 1
                patch.status['phase'] = 'JobSucceeded' if existing.status.succeeded else 'Failed'
                return
            day = f"{datetime.now(timezone.utc):%Y-%m-%d}-s{step:05d}"
            job = make_job(body, runtime, day, spec.get('deadlineSeconds', 21600))
            job['metadata']['name'] = name
            job['spec']['template']['metadata']['labels']['mnemosyne.art/job'] = name
            job['spec']['ttlSecondsAfterFinished'] = 86400
            try:
                batch.create_namespaced_job(namespace, job)
            except ApiException as exc:
                if exc.status != 409:
                    raise
            patch.status.update(phase='Running', lastJob=name, step=step,
                                observedGeneration=body['metadata']['generation'])
            return
        idle = idle_cluster(api) if policy.get('kind') == 'idle' else False
        allowed = window(policy, datetime.now(timezone.utc), idle=idle)
        if active:
            # activeDeadlineSeconds enforces clock windows. Idle loss suspends jobs;
            # suspension stops pods, retained notebook/PVC records survive.
            if not allowed:
                for job in active:
                    batch.patch_namespaced_job(job.metadata.name, namespace, {'spec': {'suspend': True}})
                patch.status['phase'] = 'WindowClosed'
            else:
                for job in active:
                    if job.spec.suspend:
                        batch.patch_namespaced_job(job.metadata.name, namespace, {'spec': {'suspend': False}})
                patch.status['phase'] = 'Running'
            return
        if not allowed:
            patch.status['phase'] = 'Waiting'
            return
        night, seconds = allowed
        name = job_name(body['metadata']['uid'], night)
        existing = next((j for j in jobs if j.metadata.name == name), None)
        if existing:
            patch.status['phase'] = 'JobSucceeded' if existing.status.succeeded else 'Failed'
            patch.status['lastJob'] = name
            return
        job = make_job(body, runtime, night, seconds)
        try:
            batch.create_namespaced_job(namespace, job)
        except ApiException as exc:
            if exc.status != 409:
                raise
        patch.status.update(phase='Running', lastJob=name, observedGeneration=body['metadata']['generation'])
