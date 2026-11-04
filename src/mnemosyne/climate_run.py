"""Reproducible mechanics experiment, without Writer or artistic decisions."""
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from .climate import year_shape
from .lineage import Lineage
from .mood import mood
from .occasions import synthetic


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scenarios', type=Path, default=Path('out/scenarios'))
    ap.add_argument('--cluster', default='shop')
    ap.add_argument('--out', type=Path, default=Path('out/works/climate'))
    ap.add_argument('--live', action='store_true')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.live:
        from .sensor import Sensor
        history_path = args.out/'sensor-private.json'
        history = json.loads(history_path.read_text()) if history_path.exists() else []
        reading = Sensor().read(history[-1] if history else None)
        if not reading['pods_observed'] and not reading['namespace_absent']:
            raise RuntimeError('pod API unavailable; no live reading claimed')
        history.append(reading)
        history_path.write_text(json.dumps(history, indent=2))
        result = {'climate': mood(history), 'missing': reading['missing'],
                  'scope': reading['scope'], 'samples': len(history),
                  'limitations': ['namespace scope only', 'RBAC effective strictness unknown',
                                  'latency unavailable', 'utilisation relative to pod requests',
                                  'image versions only; control-plane version unknown',
                                  'weekly baseline needs repeated observations']}
        (args.out/'live.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
        return
    facts = json.loads((args.scenarios/args.cluster/'facts.json').read_text())
    start = datetime.fromisoformat(facts['start'])
    life = Lineage(args.cluster, start, seed=71)
    for night in range(1, 366):
        end = start+timedelta(days=night)
        for request in synthetic(facts, end-timedelta(days=1), end, night):
            life.schedule(request)
        life.step(mood(args.scenarios, args.cluster, end))
        if night % 60 == 0:
            print('night', night, flush=True)
    works = [w for a in life.artists for w in a.catalogue]
    summary = dict(nights=life.night, artists=len(life.artists), works=len(works),
                   genres=dict(Counter(w['kind'] for w in works)), reviews=len(life.reception.reviews),
                   audience_nights=len(life.reception.logs), year_shape=year_shape(life.climate_history),
                   synthetic=True, seed=71)
    (args.out/'year.json').write_text(json.dumps(life.state(), ensure_ascii=False))
    (args.out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
