import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import yaml
from pydantic import BaseModel, ValidationError
from mnemosyne.models import Models
from mnemosyne.literature import Writer


class Answer(BaseModel):
    text: str


class MockAPI:
    def __init__(self, answer=None):
        self.requests = []
        self.answer = answer or (lambda body: {'text': 'ok'})
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append((self.path, body))
                if body['model'] == 'down':
                    self.send_response(503)
                    self.end_headers()
                    self.wfile.write(b'provider error MUST_NOT_BE_LOGGED')
                    return
                if body['model'] == 'redirect':
                    self.send_response(307)
                    self.send_header('Location', owner.url + '/stolen')
                    self.end_headers()
                    return
                answer = owner.answer(body)
                text = json.dumps(answer)
                result = ({'content': [{'type': 'text', 'text': text}], 'stop_reason': 'end_turn'}
                          if self.path.endswith('/messages') else
                          {'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]})
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}/v1'

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


def configuration(root, api, roles=None, **endpoints):
    config = {'endpoints': endpoints or {'main': dict(backend='openai', location='external',
                base_url=api.url, model='fixture', vision=True)},
              'roles': roles or {'artist': ['main']}}
    path = root/'models.yaml'
    path.write_text(yaml.safe_dump(config))
    return patch.dict(os.environ, MNEMOSYNE_MODELS=str(path), WRITER_CACHE=str(root/'cache'), WRITER='')


class ModelTests(unittest.TestCase):
    def test_roles_outage_cache_identity_images_and_credentials(self):
        with tempfile.TemporaryDirectory() as tmp, MockAPI() as api:
            root = Path(tmp)
            base = dict(backend='openai', location='external', base_url=api.url)
            with configuration(root, api, {'artist': ['bad', 'a'], 'eye': ['b']},
                               bad={**base, 'model': 'down'}, a={**base, 'model': 'a'},
                               b={**base, 'model': 'b', 'vision': True, 'key_env': 'TEST_KEY'}), \
                    patch.dict(os.environ, TEST_KEY='DONT_RETAIN_KEY'):
                nb = []
                w = Writer(nb, data_class='art')
                self.assertEqual(w.ask('art', 'climate', Answer, 'statement').text, 'ok')
                n = len(api.requests)
                w.ask('art', 'climate', Answer, 'statement')
                self.assertEqual(len(api.requests), n+1) # retry primary, cached fallback
                png = root/'draft.png'
                png.write_bytes(b'fixture image')
                w.ask('art', 'climate', Answer, 'listen', images=[png])
                body = api.requests[-1][1]
                self.assertEqual(body['model'], 'b')
                self.assertTrue(body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
                self.assertIn('schema', body['response_format']['json_schema'])
                self.assertNotIn('DONT_RETAIN_KEY', json.dumps(nb))
                self.assertNotIn('MUST_NOT_BE_LOGGED', json.dumps(nb))

    def test_private_default_and_private_fallback_never_leave_cluster(self):
        with tempfile.TemporaryDirectory() as tmp, MockAPI() as api:
            root = Path(tmp)
            base = dict(backend='openai', base_url=api.url)
            with configuration(root, api, {'artist': ['inside', 'outside']},
                               inside={**base, 'location': 'cluster', 'model': 'down'},
                               outside={**base, 'location': 'external', 'model': 'fixture'}):
                with self.assertRaises(RuntimeError):
                    Writer([]).ask('', 'PRIVATE_STATE', Answer, 'private')
                self.assertEqual([b['model'] for _, b in api.requests], ['down'])
            with configuration(root, api):
                count = len(api.requests)
                with self.assertRaises(RuntimeError):
                    Writer([]).ask('', 'PRIVATE_FACTS', Answer, 'private')
                self.assertEqual(len(api.requests), count)

    def test_anthropic_and_validation_retry(self):
        answers = [{'wrong': 'bad'}, {'text': 'valid'}]
        with tempfile.TemporaryDirectory() as tmp, MockAPI(lambda b: answers.pop(0) if answers else {'text': 'valid'}) as api:
            root = Path(tmp)
            with configuration(root, api, main=dict(backend='anthropic', model='selected',
                               base_url=api.url, vision=True)), patch.dict(os.environ, WRITER=''):
                self.assertEqual(Writer([], data_class='art').ask('', '', Answer, 'test').text, 'valid')
                self.assertEqual(len(api.requests), 2)
                self.assertEqual(api.requests[0][0], '/v1/messages')
                self.assertIn('format', api.requests[0][1]['output_config'])
                png = root/'draft.png'
                png.write_bytes(b'fixture image')
                Writer([], data_class='art').ask('', '', Answer, 'look', images=[png])
                source = api.requests[-1][1]['messages'][0]['content'][1]['source']
                self.assertEqual(source['media_type'], 'image/png')
                self.assertEqual(source['type'], 'base64')

    def test_role_routing_and_model_cache_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp, MockAPI() as api:
            root = Path(tmp)
            base = dict(backend='openai', base_url=api.url)
            with configuration(root, api, {'artist': ['a'], 'critic': ['c'], 'chronicler': ['h']},
                               a={**base, 'model': 'artist'}, c={**base, 'model': 'critic'},
                               h={**base, 'model': 'chronicler'}):
                writer = Writer([], data_class='art')
                for step in ('statement', 'interrogation:0', 'lives-chapter'):
                    writer.ask('', 'art', Answer, step)
                self.assertEqual([b['model'] for _, b in api.requests], ['artist', 'critic', 'chronicler'])
                writer.config.endpoints['a'].model = 'replacement'
                writer.ask('', 'art', Answer, 'statement')
                self.assertEqual(api.requests[-1][1]['model'], 'replacement')

    def test_no_redirect_and_no_implicit_model(self):
        with patch.dict(os.environ, {'WRITER': '', 'MNEMOSYNE_MODELS': ''}, clear=False):
            with self.assertRaisesRegex(RuntimeError, 'no model configured'):
                Writer([]).ask('', '', Answer, 'test')
        with tempfile.TemporaryDirectory() as tmp, MockAPI() as api:
            with configuration(Path(tmp), api, main=dict(backend='openai', base_url=api.url,
                                                        model='redirect', attempts=1)):
                with self.assertRaises(RuntimeError):
                    Writer([], data_class='art').ask('', '', Answer, 'test')
                self.assertEqual(len(api.requests), 1)

    def test_config_rejects_embedded_credentials_unknown_keys_and_nondev_cli(self):
        for endpoint in ({'backend': 'codex'}, {'backend': 'openai', 'model': 'm', 'base_url': 'https://secret@host/v1'},
                         {'backend': 'none', 'api_key': 'secret'}):
            with self.assertRaises(ValidationError):
                Models.model_validate({'endpoints': {'bad': endpoint}})

    def test_complete_external_mock_night_and_privacy_projection(self):
        from mnemosyne.artist import Statement, self_portrait
        from mnemosyne.lineage import Lineage
        from mnemosyne.music.composer import Night
        plan = json.loads(Path('src/mnemosyne/music/schools/plans/tintinnabuli.json').read_text())
        def answer(body):
            schema = body['response_format']['json_schema']['schema']
            title = schema['title']
            if title == 'Statement':
                return {k: [] if f.annotation == list[str] else 'fixture idea'
                        for k, f in Statement.model_fields.items()}
            if title == 'SelfPortrait':
                return dict(inner_critic={}, name='Fixture', portrait='art', wounds=[], loves=[], fears=[], what_i_am_as_artist='art')
            if title == 'Interrogation':
                return dict(verdict='accept', reasons='fixture', keep='', weak_answers=[], cliches_found=[], questions_back=[])
            if title == 'Method':
                return dict(kind='school', school='tintinnabuli', sources=['tintinnabuli'], principle='triad',
                            transformation='', concept='fixture', reason='fixture', notagen_prompt='', form='school')
            if title == 'Halftones':
                shade = dict(shade='fixture', why_mine='fixture', how_it_shows='fixture')
                return dict(thought=shade, embodiment=shade, nuances=[], overall='fixture')
            if title == 'PlanText':
                return dict(plan_json=json.dumps(plan), note='fixture')
            if title == 'Listening':
                return dict(verdict='accept', reasons='mock, not aesthetic evidence', corrections=[], matters=True, quality=.5)
            if title == 'Chapter':
                return dict(text='fixture chronicle')
            if title == 'ReviewWords':
                return dict(text='fixture opinion')
            if title == 'LifeWords':
                return {k: '' for k in schema['properties']}
            raise AssertionError(title)
        class FixtureStudio:
            def run(self, request, destination):
                folder = destination/'result'
                folder.mkdir(parents=True)
                (folder/'score.musicxml').write_text('fixture; not a composition')
                (folder/'page.png').write_bytes(b'fixture')
                return dict(score='score.musicxml', images=['page.png'], analysis={'parts': 2, 'bpm': 48})
        with tempfile.TemporaryDirectory() as tmp, MockAPI(answer) as api:
            root = Path(tmp)
            with configuration(root, api):
                start = time.monotonic()
                self_portrait({'born': 'PRIVATE_BIRTH', 'state': 'PRIVATE_STATE', 'teachers': ['Bach']}, [])
                life = Lineage('PRIVATE_CLUSTER', datetime(2025, 1, 1))
                a = life.artists[0]
                a.portrait = 'fixture art'
                a.teachers.append(a.id)
                a.inner_critic['history'].append({'private': 'PRIVATE_TASTE'})
                for chapter in life.biographies[a.id].chapters:
                    chapter['facts']['sentinel'] = 'PRIVATE_FACTS'
                    chapter['state']['sentinel'] = 'PRIVATE_SNAPSHOT'
                night = Night(life, a.id, root/'night', FixtureStudio())
                result = night.run('quiet', drafts=1)
                self.assertEqual(result['status'], 'accepted')
                life.write_words()
                life.reception.register(a, a.catalogue[-1])
                life.reception.review(a.catalogue[-1]['id'], life.reception.critics[0], 1)
                life.reception.write_words()
                wire = json.dumps(api.requests)
                for sentinel in ('PRIVATE_BIRTH', 'PRIVATE_STATE', 'PRIVATE_CLUSTER', 'PRIVATE_FACTS', 'PRIVATE_SNAPSHOT', 'PRIVATE_TASTE'):
                    self.assertFalse(sentinel in wire, sentinel)
                self.assertEqual(len(result['sketches']), 2)
                import resource, sys
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
                print(f'process peak RSS: {peak} bytes (includes interpreter and fixtures)')
                print(f'mock external night: {time.monotonic()-start:.3f}s, {len(api.requests)} requests; quality not measured')

    def test_chamber_does_not_invoke_writer_or_import_torch(self):
        import sys
        from mnemosyne.lineage import Lineage
        with patch.dict(os.environ, WRITER='', MNEMOSYNE_MODELS=''), \
                patch.object(Writer, 'ask', side_effect=AssertionError('model in chamber')):
            life = Lineage('chamber', datetime(2025, 1, 1))
            from mnemosyne.mood import mood
            # State mechanics is model-free; school composition is a deterministic rule engine.
            from mnemosyne.music.schools import SCHOOLS
            plan = json.loads(Path('src/mnemosyne/music/schools/plans/tintinnabuli.json').read_text())
            score = SCHOOLS['tintinnabuli'].compose(plan, plan['seed'])
            self.assertTrue(list(score.recurse().notes))
            self.assertNotIn('torch', sys.modules)


class LooseSchemaTests(unittest.TestCase):
    def test_bounds_are_dropped_for_the_api_only(self):
        from mnemosyne.models import loose
        s = {'type': 'object', 'properties': {'q': {'type': 'number', 'minimum': 0, 'maximum': 1}}}
        self.assertEqual(loose(s), {'type': 'object', 'properties': {'q': {'type': 'number'}}})
