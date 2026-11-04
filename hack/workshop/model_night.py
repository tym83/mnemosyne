"""Run INSIDE a studio pod. No CLIs, no Secret reads; retain every artifact.

--preflight reports available cgroup memory without loading anything.
--spec is JSON: models, lineage, inner (paths), servers (command/health), drafts.
The same lineage/inner files are the comparison input for both endpoint paths.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import time
from urllib.request import urlopen


def memory():
    root = Path('/sys/fs/cgroup')
    current = int((root/'memory.current').read_text())
    raw = (root/'memory.max').read_text().strip()
    limit = int(raw) if raw != 'max' else None
    return dict(current_bytes=current, limit_bytes=limit,
                available_bytes=limit-current if limit else None)


def preflight(required):
    result = memory()
    result.update(required_bytes=required, ready=result['available_bytes'] is not None
                  and result['available_bytes'] >= required)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--required-gib', type=float, default=26)
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    check = preflight(int(args.required_gib * 2**30))
    if args.preflight:
        print(json.dumps(check))
        return 0 if check['ready'] else 2
    if not args.spec or not args.out:
        parser.error('--spec and --out required')
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(preflight=check, status='blocked_memory', quality='not assessed')
    report_file = args.out/'measurement.json'
    report_file.write_text(json.dumps(report, indent=2))
    if not check['ready']:
        return 2
    report['status'] = 'running'
    spec = json.loads(args.spec.read_text())
    os.environ['MNEMOSYNE_MODELS'] = str(Path(spec['models']).resolve())
    os.environ['WRITER_CACHE'] = str(args.out/'cache')
    os.environ.pop('WRITER', None)
    from mnemosyne.models import Models
    config = Models.load()
    if any(e.backend in ('codex', 'claude') for e in config.endpoints.values()):
        raise ValueError('benchmark must not invoke developer subscriptions')
    # No remote files or Secret objects are collected. Input fingerprints stay local.
    for key in ('lineage', 'inner', 'models'):
        report[key + '_sha256'] = hashlib.sha256(Path(spec[key]).read_bytes()).hexdigest()
    stop = threading.Event()
    samples = []
    def sample():
        while not stop.is_set():
            samples.append(memory()['current_bytes'])
            stop.wait(1)
    monitor = threading.Thread(target=sample, daemon=True)
    processes, logs = [], []
    start = time.monotonic()
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    def deadline(signum, frame):
        raise TimeoutError('work window ended')
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(spec.get('deadline_seconds', 21600))
    monitor.start()
    try:
        for i, server in enumerate(spec.get('servers', [])):
            log = (args.out/f'server-{i}.log').open('w')
            logs.append(log)
            process = subprocess.Popen(['nice', '-n', '19', *server['command']], stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(process)
            deadline = time.monotonic() + server.get('startup_seconds', 900)
            while True:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('model server did not become ready; inspect retained log')
                try:
                    with urlopen(server['health'], timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                time.sleep(1)
        report['load_seconds'] = time.monotonic()-start
        from mnemosyne.lineage import Lineage
        from mnemosyne.music.composer import Night
        class LocalStudio:
            def run(self, request, destination):
                destination.mkdir(parents=True)
                path = destination/'request.json'
                path.write_text(json.dumps(request))
                with (destination/'worker.log').open('w') as log:
                    subprocess.run([sys.executable, '-m', 'mnemosyne.music.composer_worker',
                                    str(path), '--out', str(destination/'result')],
                                   stdout=log, stderr=subprocess.STDOUT, check=True, timeout=14400)
                return json.loads((destination/'result/result.json').read_text())
        life = Lineage.restore(json.loads(Path(spec['lineage']).read_text()))
        artist = spec.get('artist') or next(a.id for a in life.artists if a.status == 'working')
        night = Night(life, artist, args.out/'night', LocalStudio())
        result = night.run(Path(spec['inner']).read_text(), drafts=spec.get('drafts', 3))
        report.update(status=result['status'], model_verdict=result.get('verdict'),
                      quality='model notes only; human comparison pending')
    except BaseException as exc:
        report.update(status='failed', error_type=type(exc).__name__)
        raise
    finally:
        signal.alarm(0)
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        for log in logs:
            log.close()
        stop.set()
        monitor.join()
        report.update(seconds=time.monotonic()-start,
                      cgroup_peak_sampled_bytes=max(samples, default=0),
                      cgroup_peak_includes_other_jobs=True,
                      largest_child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                      memory_after=memory(), servers_stopped=all(p.poll() is not None for p in processes))
        report_file.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
