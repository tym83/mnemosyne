"""Model policy, with no SDK imports or model loads in chamber mode.

Credentials are supplied by Kubernetes secretKeyRef -> environment, never by
reading the Kubernetes API. Configuration and notebook identities contain no keys.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Literal
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Endpoint(BaseModel):
    model_config = ConfigDict(extra='forbid')
    backend: Literal['openai', 'anthropic', 'codex', 'claude', 'none'] = 'none'
    location: Literal['external', 'cluster', 'dev'] = 'external'
    base_url: str = ''
    model: str = ''
    key_env: str | None = None
    vision: bool = False
    structured: Literal['json_schema', 'json_object', 'prompt'] = 'json_schema'
    timeout: float = Field(default=300, gt=0)
    max_tokens: int = Field(default=8192, gt=0)
    attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode='after')
    def check(self):
        from urllib.parse import urlsplit
        if self.backend in ('codex', 'claude') and self.location != 'dev':
            raise ValueError('CLI backends are development-only')
        if self.backend in ('openai', 'anthropic'):
            u = urlsplit(self.base_url)
            if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment:
                raise ValueError('base_url must be an HTTP(S) endpoint without credentials/query')
            if not self.model:
                raise ValueError('model is required')
        if self.backend == 'anthropic' and self.location != 'external':
            raise ValueError('Anthropic is an external API')
        return self


class Models(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoints: dict[str, Endpoint] = Field(default_factory=dict)
    roles: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def check(self):
        for role, names in self.roles.items():
            if role not in ('artist', 'critic', 'chronicler', 'eye') or not names:
                raise ValueError('roles: artist, critic, chronicler, eye; nonempty fallback lists')
            if any(n not in self.endpoints for n in names):
                raise ValueError('unknown endpoint in role')
        return self

    @classmethod
    def load(cls):
        path = os.environ.get('MNEMOSYNE_MODELS')
        return cls.model_validate(yaml.safe_load(Path(path).read_text()) or {}) if path else cls()

    def route(self, role):
        names = self.roles.get(role, self.roles.get('artist', []))
        return [(n, self.endpoints[n]) for n in names]


def role_for(step, images=False):
    if images:
        return 'eye'
    if step.startswith(('life:', 'lives-', 'chronicle')):
        return 'chronicler'
    if step.startswith(('interrogation', 'method-judgement', 'verdict', 'listen:', 'plate-judgement', 'review')):
        return 'critic'
    return 'artist'


class NoRedirect(HTTPRedirectHandler):
    # A redirect must not forward prompts, image bytes or credentials elsewhere.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Keywords Anthropic structured outputs refuse (400 on a 'quality' bounded 0..1, found on the first real
# install). The answer is still validated locally against the full schema by pydantic.
UNSUPPORTED = ('minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf',
               'minLength', 'maxLength', 'pattern', 'format', 'maxItems')


def loose(schema):
    if isinstance(schema, dict):
        return {k: loose(v) for k, v in schema.items() if k not in UNSUPPORTED}
    if isinstance(schema, list):
        return [loose(v) for v in schema]
    return schema


def request(endpoint, system, prompt, schema, max_tokens, images=None):
    blocks = []
    for path in images or []:
        mime = mimetypes.guess_type(str(path))[0]
        if mime not in ('image/png', 'image/jpeg', 'image/webp', 'image/gif'):
            raise ValueError('unsupported draft image format')
        blocks.append((mime, base64.b64encode(Path(path).read_bytes()).decode()))
    headers = {'Content-Type': 'application/json'}
    if endpoint.key_env:
        key = os.environ.get(endpoint.key_env)
        if not key:
            raise RuntimeError('configured credential is unavailable')
        headers['Authorization' if endpoint.backend == 'openai' else 'x-api-key'] = (
            'Bearer ' + key if endpoint.backend == 'openai' else key)
    if endpoint.structured == 'prompt':
        system += '\nReturn only JSON matching this schema:\n' + json.dumps(schema)
    limit = min(max_tokens, endpoint.max_tokens)
    if endpoint.backend == 'openai':
        content = [{'type': 'text', 'text': prompt}] + [
            {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{data}'}} for mime, data in blocks]
        body = {'model': endpoint.model, 'messages': [
            {'role': 'system', 'content': system}, {'role': 'user', 'content': content}], 'max_tokens': limit}
        if endpoint.structured == 'json_schema':
            body['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'answer', 'strict': True, 'schema': schema}}
        elif endpoint.structured == 'json_object':
            body['response_format'] = {'type': 'json_object'}
            body['messages'][0]['content'] += '\nReturn JSON matching: ' + json.dumps(schema)
        path = '/chat/completions'
    else:
        headers['anthropic-version'] = '2023-06-01'
        body = {'model': endpoint.model, 'max_tokens': limit, 'system': system,
                'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}] + [
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': mime, 'data': data}}
                    for mime, data in blocks]}]}
        if endpoint.structured == 'json_schema':
            body['output_config'] = {'format': {'type': 'json_schema', 'schema': loose(schema)}}
        elif endpoint.structured == 'json_object':
            body['system'] += '\nReturn JSON matching: ' + json.dumps(schema)
        path = '/messages'
    req = Request(endpoint.base_url.rstrip('/') + path, json.dumps(body).encode(), headers)
    try:
        with build_opener(NoRedirect()).open(req, timeout=endpoint.timeout) as response:
            result = json.load(response)
    except HTTPError as exc:
        # Provider errors may echo the key or private prompt. Never retain bodies.
        exc.close()
        error = RuntimeError(f'model HTTP {exc.code}')
        error.status_code = exc.code
        raise error from None
    if endpoint.backend == 'openai':
        choice = result['choices'][0]
        if choice.get('finish_reason') not in (None, 'stop'):
            raise ValueError('incomplete model answer')
        answer = choice['message']['content']
    else:
        if result.get('stop_reason') not in (None, 'end_turn'):
            raise ValueError('incomplete model answer')
        answer = ''.join(b['text'] for b in result['content'] if b['type'] == 'text')
    return answer, {'engine': endpoint.model, 'usage': result.get('usage', {})}
