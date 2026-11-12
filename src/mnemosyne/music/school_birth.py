"""Birth of a school: an artist's manifesto becomes a grammar as code.

The artist writes the grammar; nothing here judges its beauty. A grammar is
admitted only if it is safe (a small import and name allowlist, no dunder
access), deterministic, playable by the existing instruments, carries the
standard school surface (so its works decode without its code), and differs
measurably from every school that already exists, by a margin taken from how
far the existing schools are from each other. The artist's inner critic then
accepts or rejects it, like any other work. Rejected attempts are retained.

Trials run in an isolated child process with CPU and memory limits.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

from pydantic import BaseModel

ALLOWED_IMPORTS = {'math', 'fractions', 'itertools', 'functools', 'statistics', 'collections',
                   'music21', 'music21.note', 'music21.chord', 'music21.dynamics', 'music21.expressions',
                   'music21.articulations', 'music21.stream', 'music21.pitch', 'music21.duration',
                   'music21.tempo', 'music21.meter', 'music21.spanner'}
ALLOWED_RELATIVE = {'common', 'material', 'choices'}
FORBIDDEN_NAMES = {'open', 'exec', 'eval', 'compile', '__import__', 'globals', 'locals', 'vars',
                   'getattr', 'setattr', 'delattr', 'input', 'breakpoint', 'exit', 'quit', 'help',
                   'memoryview', 'type', 'object', 'super', 'classmethod', 'staticmethod', 'property'}
# The surface codec the decoder knows; a school may choose its knot period.
SURFACE = {'levels': 16, 'step_percent': .25, 'max_deviation_percent': 1.875}
PERIODS = {.25, .5, 1., 2.}
MIN_BYTES_PER_3_MIN = 32
EXAMPLES = ('drone', 'additive')


class GrammarText(BaseModel):
    source: str  # a Python module: compose(plan, seed, *, choices=None) and FREE_CHANNELS
    plan_json: str  # one complete plan for the new school
    diary: str


def school_id(name: str) -> str:
    slug = ''.join(c if c.isascii() and c.isalnum() else '-' for c in name.lower()).strip('-')
    slug = '-'.join(p for p in slug.split('-') if p)[:24] or 'school'
    return f'born-{slug}-{hashlib.sha256(name.encode()).hexdigest()[:6]}'


def check(source: str) -> list[str]:
    """Static admission; returns problems, empty when admitted."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f'syntax error: {exc}']
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            problems += [f'import {a.name} is not allowed' for a in node.names if a.name not in ALLOWED_IMPORTS]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module in ALLOWED_RELATIVE:
                continue
            if node.level or node.module not in ALLOWED_IMPORTS:
                problems.append(f'from {"." * node.level}{node.module or ""} import is not allowed')
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f'name {node.id} is not allowed')
        elif isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            problems.append(f'private attribute {node.attr} is not allowed')
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await, ast.ClassDef)):
            problems.append(f'{type(node).__name__} is not allowed')
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if 'compose' not in names:
        problems.append('define compose(plan, seed, *, choices=None)')
    if not any(isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'FREE_CHANNELS' for t in n.targets)
               for n in tree.body):
        problems.append('define FREE_CHANNELS')
    return problems


def load(name: str, source: str):
    problems = check(source)
    if problems:
        raise ValueError('; '.join(problems))
    module = types.ModuleType(f'mnemosyne.music.schools.{name}')
    module.__package__ = 'mnemosyne.music.schools'
    module.__source__ = source
    exec(compile(source, f'<school {name}>', 'exec'), module.__dict__)
    rules = getattr(module, 'FREE_CHANNELS', None)
    if not isinstance(rules, dict) or any(rules.get(k) != v for k, v in SURFACE.items()) \
            or rules.get('period_quarters') not in PERIODS:
        raise ValueError(f'FREE_CHANNELS must keep the standard surface {SURFACE} '
                         f'and a period_quarters in {sorted(PERIODS)}')
    return module


def register(name: str, source: str, plan: dict | None = None):
    from .schools import SCHOOLS
    if name in SCHOOLS and getattr(SCHOOLS[name], '__source__', None) == source:
        return SCHOOLS[name]
    if name in SCHOOLS and not hasattr(SCHOOLS[name], '__source__'):
        raise ValueError('a born school cannot replace a founding school')
    module = load(name, source)
    module.__plan__ = plan
    SCHOOLS[name] = module
    sys.modules[module.__name__] = module
    return module


def register_all(schools: dict):
    for name, record in schools.items():
        if record.get('status', 'accepted') == 'accepted':
            register(name, record['source'], record.get('plan'))


def source_of(name: str) -> str:
    from .schools import SCHOOLS
    module = SCHOOLS[name]
    return getattr(module, '__source__', None) or Path(module.__file__).read_text()


def _events(score):
    return [[(float(n.offset), float(n.quarterLength), [p.ps for p in n.pitches]) for n in part.recurse().notes]
            for part in score.parts]


def _features(name, plan):
    from .distinctness import features
    from .schools import SCHOOLS
    return features(SCHOOLS[name].compose(plan, plan['seed']).toSoundingPitch(), plan['tempo'])


def _trial(request):
    """Child process body: everything that executes the artist's code."""
    from .distinctness import compare
    from .schools import SCHOOLS
    from .schools.common import analyze, validate
    from .schools.plan import SchoolPlan
    from ..weave import schools as surface_codec, surface
    name, plan = request['name'], request['plan']
    report = {'name': name, 'errors': []}
    try:
        register(name, request['source'])
        if plan.get('school') != name:
            raise ValueError(f'plan.school must be {name}')
        SchoolPlan.model_validate(plan)
        validate(plan)
        module = SCHOOLS[name]
        first = module.compose(plan, plan['seed'])
        if _events(first) != _events(module.compose(plan, plan['seed'])):
            raise ValueError('compose is not deterministic for one seed')
        analyze(first, plan)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'demo.musicxml'
            first.write('musicxml', fp=path)
            root = surface_codec.prepare(surface.read(path), name)
            capacity = surface_codec.capacity(root)
            per_3_min = capacity * 180 / plan['duration']
            if per_3_min < MIN_BYTES_PER_3_MIN:
                raise ValueError(f'surface carries {per_3_min:.0f} bytes per three minutes; '
                                 f'at least {MIN_BYTES_PER_3_MIN} are needed (more sounding time)')
            block = os.urandom(capacity)
            woven = path.with_name('woven.musicxml')
            surface.write(surface_codec.encode(root, block), woven)
            if surface_codec.decode(surface.read(woven)) != block:
                raise ValueError('surface round trip failed')
        report['capacity_bytes'] = capacity
        report['bytes_per_3_min'] = round(per_3_min, 1)
        plans = Path(__file__).parent/'schools/plans'
        items = {other: _features(other, json.loads((plans/f'{other}.json').read_text()))
                 for other in request['existing'] if (plans/f'{other}.json').exists()}
        items.update({other: _features(other, p) for other, p in request.get('born_plans', {}).items()})
        founding = compare(items)
        nearest_neighbour = {}
        for p in founding.get('all_pairs', []):
            for a, b in ((p['a'], p['b']), (p['b'], p['a'])):
                nearest_neighbour[a] = min(nearest_neighbour.get(a, 1e9), p['distance'])
        mine = compare({**items, name: _features(name, plan)})
        own = sorted((p for p in mine['all_pairs'] if name in (p['a'], p['b'])), key=lambda p: p['distance'])
        margin = sorted(nearest_neighbour.values())[len(nearest_neighbour)//2] / 2
        report.update(nearest={'school': own[0]['b'] if own[0]['a'] == name else own[0]['a'],
                               'distance': round(own[0]['distance'], 4),
                               'by_feature': own[0]['by_feature']},
                      margin=round(margin, 4), distinct=own[0]['distance'] >= margin,
                      features=mine['features'][name])
    except Exception as exc:  # the artist's code may fail in any way
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    return report


def trial(name: str, source: str, plan: dict, *, existing=None, born_plans=None, timeout=900) -> dict:
    """Run _trial in a limited, isolated interpreter."""
    problems = check(source)
    if problems:
        return {'name': name, 'errors': problems}
    from .schools import SCHOOLS
    request = {'name': name, 'source': source, 'plan': plan,
               'existing': sorted(existing if existing is not None else
                                  (n for n, m in SCHOOLS.items() if not hasattr(m, '__source__'))),
               'born_plans': born_plans or {}}
    package = str(Path(__file__).resolve().parents[2])
    code = (f'import sys; sys.path.insert(0, {package!r}); '
            'from mnemosyne.music.school_birth import _child; _child()')
    def limits():
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
        if sys.platform != 'darwin':
            resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    try:
        done = subprocess.run([sys.executable, '-I', '-c', code], input=json.dumps(request), text=True,
                              capture_output=True, timeout=timeout, preexec_fn=limits,
                              env={'PATH': os.environ.get('PATH', ''), 'HOME': tempfile.gettempdir()})
    except subprocess.TimeoutExpired:
        return {'name': name, 'errors': [f'trial exceeded {timeout} s']}
    lines = done.stdout.strip().splitlines()
    if done.returncode or not lines:
        return {'name': name, 'errors': [f'trial process failed: {done.stderr.strip()[-800:]}']}
    return json.loads(lines[-1])


def _child():
    print(json.dumps(_trial(json.loads(sys.stdin.read())), ensure_ascii=False))


def contract() -> dict:
    here = Path(__file__).parent/'schools'
    return {
        'module': 'Python module. Define compose(plan, seed, *, choices=None) returning a music21 Score, '
                  'and FREE_CHANNELS. Use setup(plan, seed, <school id>, choices=choices) -> (score, rng, sections, total), '
                  'put(part, at, length, pitch_or_None), finish(score, total) from .common; fit/mark from .material. '
                  'All randomness through rng (rng.choice, rng.random, rng.uniform, rng.randint). '
                  'Times are quarter notes. Monophonic parts: no overlapping events in one part.',
        'imports': sorted(ALLOWED_IMPORTS) + [f'.{m}' for m in sorted(ALLOWED_RELATIVE)],
        'forbidden': sorted(FORBIDDEN_NAMES) + ['private attributes (_x)', 'classes', 'global/nonlocal'],
        'free_channels': {**SURFACE, 'period_quarters': 'one of ' + str(sorted(PERIODS)),
                          'dynamics': 'one sentence: what stays fixed and what may breathe'},
        'admission': ['deterministic for a seed',
                      'every part sounds within its instrument range',
                      f'at least {MIN_BYTES_PER_3_MIN} bytes per three minutes on the surface (sustained sound)',
                      'measurably distinct from every existing school'],
        'plan_schema': json.loads((here/'plans/drone.json').read_text()),
        'common': (here/'common.py').read_text(),
        'examples': {name: (here/f'{name}.py').read_text() for name in EXAMPLES},
    }


def found(manifesto: dict, ask, artist_system: str, critic_system: str, *, rounds=3,
          born_plans=None) -> tuple[dict | None, list]:
    """The artist turns a manifesto into a grammar; trial and inner critic decide."""
    from ..artist import Judgement, accepted
    name = school_id(manifesto['name'])
    history = []
    prompt = json.dumps({'task': f'Your new school is {manifesto["name"]!r} (id {name}). Write its grammar as code, '
                                 'so that the rules embody the manifesto rather than decorate an existing school. '
                                 'Also write one complete plan for it in plan_json.',
                         'manifesto': manifesto, 'contract': contract()}, ensure_ascii=False)
    for r in range(rounds):
        grammar = ask(artist_system, prompt, GrammarText, f'school-grammar:{r}')
        attempt = {'round': r, 'source': grammar.source, 'plan_json': grammar.plan_json, 'diary': grammar.diary}
        history.append(attempt)
        try:
            plan = json.loads(grammar.plan_json)
        except json.JSONDecodeError as exc:
            attempt['trial'] = {'errors': [f'plan_json: {exc}']}
            prompt += '\n\nThe plan is not valid JSON: ' + str(exc)
            continue
        report = trial(name, grammar.source, plan, born_plans=born_plans)
        attempt['trial'] = report
        if report['errors']:
            prompt += '\n\nThe grammar failed its trial; fix it without abandoning the manifesto: ' + '; '.join(report['errors'])
            continue
        if not report['distinct']:
            prompt += (f"\n\nMeasured: the grammar sounds like {report['nearest']['school']} "
                       f"(distance {report['nearest']['distance']} < margin {report['margin']}; "
                       f"by feature {report['nearest']['by_feature']}). It renames an existing school. "
                       'Change the rules where the manifesto differs.')
            continue
        judgement = ask(critic_system, json.dumps({'manifesto': manifesto, 'diary': grammar.diary,
                                                   'measured': {k: report[k] for k in ('nearest', 'margin', 'bytes_per_3_min')},
                                                   'grammar': grammar.source}, ensure_ascii=False),
                        Judgement, f'school-judgement:{r}', max_tokens=8000)
        attempt['judgement'] = judgement.model_dump()
        if accepted(judgement.verdict):
            return {'id': name, 'name': manifesto['name'], 'manifesto': manifesto, 'source': grammar.source,
                    'plan': plan, 'trial': report, 'judgement': judgement.model_dump(),
                    'status': 'accepted'}, history
        prompt += '\n\nYour inner critic objected: ' + '; '.join(judgement.objections) + \
                  (f' It resembles {judgement.is_reinvention_of}.' if judgement.is_reinvention_of else '')
    return None, history
