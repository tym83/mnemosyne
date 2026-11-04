"""Ten-year synthetic reception experiment; run CPU experiments in a studio pod."""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from .lineage import Lineage, Parameters
from .weave import fountain


def examples(life):
    r = life.reception
    found = {}
    for review in r.reviews:
        w = r.works[review['work']]
        if w['private_merit'] >= .8 and review['score'] <= .25:
            found.setdefault('Misjudged masterpiece', dict(work=review['work'], review=review['id'], night=review['night']))
        if w['private_merit'] <= .4 and review['score'] >= .75:
            found.setdefault('Praised failure', dict(work=review['work'], review=review['id'], night=review['night']))
    for e in r.releases:
        w = r.works[e['work']]
        later = [v for v in r.reviews if v['work'] == e['work'] and v['night'] >= e['night'] and v['score'] >= .7]
        if e['posthumous'] and later:
            found.setdefault('Posthumous rediscovery', dict(work=e['work'], edition=e['id'], night=e['night']))
            if e['raw'] and w['private_merit'] >= .7:
                found.setdefault('Fine music from the notebooks', dict(work=e['work'], edition=e['id'], night=e['night'], review=later[0]['id']))
    for wid,w in r.works.items():
        if w['peak'] >= 50 and w['curve'] and w['curve'][-1][0] < life.night-365:
            found.setdefault('Fall into oblivion', dict(work=wid, last_listening=w['curve'][-1][0]))
    return found


def report(life, out):
    out.mkdir(parents=True, exist_ok=True)
    r = life.reception
    found = examples(life)
    (out/'state.json').write_text(json.dumps(life.state(), ensure_ascii=False, separators=(',', ':')))
    for name, records, fields in (
        ('works.csv', [dict(id=k, **{f:v[f] for f in ('artist','night','private_merit','original_verdict','total','peak')}) for k,v in r.works.items()],
         ['id','artist','night','private_merit','original_verdict','total','peak']),
        ('reviews.csv', r.reviews, ['id','work','edition','night','critic','score','revision_of','text']),
        ('curves.csv', [dict(work=k, night=n, count=c) for k,v in r.works.items() for n,c in v['curve']], ['work','night','count'])):
        with (out/name).open('w') as f:
            writer = csv.DictWriter(f, fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(records)
    gross = sum(len(log['timestamps_ms']) for log in r.logs)
    active = sum(bool(log['timestamps_ms']) for log in r.logs)
    lines = ['# Reception: ten synthetic years', '',
             f'Seed {life.seed}; {life.night} nights; {len(life.artists)} composers; '
             f'{sum(a.status == "dead" for a in life.artists)} deaths; {len(r.works)} works; {len(r.reviews)} reviews.', '',
             'No LLM calls. Merit and examples are numerical simulation diagnostics, not verdicts on real music.',
             'Masterpiece: merit ≥ .8 and review ≤ .25; failure: merit ≤ .4 and review ≥ .75. '
             'Notebook discovery: merit ≥ .7 and a later review ≥ .7. Oblivion: former peak ≥ 50, no listening for a year.', '',
             f'Capacity: 256 gross bytes / {256-fountain.OVERHEAD} envelope bytes per active night; '
             f'{active} active nights, {life.night-active} empty nights. Mean gross {gross/life.night:.2f} '
             f'and net {active*(256-fountain.OVERHEAD)/life.night:.2f} bytes/night. '
             'Subtract 72 bytes per encrypted snapshot and redundancy; reviews currently carry 0 embedded bytes.', '',
             '[All works and merit](works.csv), [reviews over time](reviews.csv), '
             '[nightly popularity curves](curves.csv), [resumable state](state.json). '
             'Missing curve rows mean zero listens. Counts include synthetic listeners; programme timestamps describe a sampled panel.', '']
    for name, case in found.items():
        w = r.works[case['work']]
        a = next(a for a in life.artists if a.id == w['artist'])
        lines += [f'## {name}', '', f'`{case["work"]}`: merit {w["private_merit"]:.3f}; original verdict '
                  f'{w["original_verdict"]}; composer died on night {a.death_night}. Evidence: `{json.dumps(case)}`.', '',
                  'Annual listening totals: ' + ' → '.join(str(sum(c for n,c in w['curve'] if y*365 < n <= (y+1)*365)) for y in range(10)), '']
        if 'edition' in case:
            edition = next(e for e in r.releases if e['id'] == case['edition'])
            before = r.logs[max(0, edition['night']-2)]['outcomes'][a.id]
            after = r.logs[min(life.night-1, edition['night']+30)]['outcomes'][a.id]
            lines += [f"Edition {edition['id']}: {sum(c for _,c in edition['curve'])} listens; "
                      f"{len(edition['reviews'])} reviews. Composer fame/wealth before: {before}; 30 nights later: {after}.", '']
        for v in [v for v in r.reviews if v['work'] == case['work']]:
            lines.append(f'- Night {v["night"]}, {v["critic"]}: {v["score"]:.3f}. {v["text"]}')
        lines.append('')
    lines += ['## Composer outcomes', '', '| Composer | Status | Fame | Wealth |', '|---|---|---:|---:|']
    lines += [f'| {a.id} | {a.status} | {a.recognition:.3f} | {a.wealth:.3f} |' for a in life.artists]
    lines += ['', 'Verification: deterministic checkpoint continuation, preserved notebook editions, frame recovery '
              'after 25% loss, tamper rejection and uniform timing statistics are covered by test_reception.py.', '',
              'Suggested commits (each with --signoff and exactly one Assisted-by: LLM trailer):',
              '- `feat: model fallible taste and shared reception in artist lineages`',
              '- `feat: carry backup frames in audience timing logs`',
              '- `test: document and validate ten-year reception histories`', '']
    missing = {'Misjudged masterpiece','Praised failure','Posthumous rediscovery','Fine music from the notebooks','Fall into oblivion'} - found.keys()
    if missing: lines += ['Missing cases: ' + ', '.join(sorted(missing))]
    (out/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps(dict(seed=life.seed, nights=life.night, works=len(r.works), reviews=len(r.reviews), examples=found, missing=sorted(missing)), indent=2), flush=True)
    return missing


def plot_curves(state_path, out):
    """Render diagnostic curves without running the simulation again."""
    import os
    import tempfile
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'atelier-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    life = Lineage.restore(json.loads(Path(state_path).read_text()))
    cases = examples(life)
    fig, axes = plt.subplots(len(cases), 1, figsize=(11, 11), sharex=True)
    for ax, (label, case) in zip(axes, cases.items()):
        work = life.reception.works[case['work']]
        counts = dict(work['curve'])
        ax.plot(range(1, life.night+1), [counts.get(n, 0) for n in range(1, life.night+1)], linewidth=.7)
        ax.set_title(f"{label}: {case['work']} (merit {work['private_merit']:.3f})", fontsize=10)
        ax.set_ylabel('Listens/night')
        if 'edition' in case:
            ax.axvline(case['night'], color='darkred', linestyle='--', linewidth=.8)
        ax.grid(alpha=.2)
    axes[-1].set_xlabel('Night')
    fig.tight_layout()
    fig.savefig(Path(out)/'popularity.png', dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seed', type=int, default=17)
    ap.add_argument('--out', type=Path, default=Path('out/works/reception'))
    args = ap.parse_args()
    life = Lineage('atelier', datetime(2025, 1, 1), args.seed, Parameters(synthetic_schools=True))
    for n in range(3650):
        weight = .8 if n//730 % 3 else .2
        life.step(dict(strain=weight, loss=weight, scars=weight, turbulence=weight))
    if report(life, args.out):
        raise SystemExit("required reception cases missing; see REPORT.md")


if __name__ == '__main__':
    main()
