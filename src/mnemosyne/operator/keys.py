"""Resolve externally managed recipient keys without reading the Kubernetes API."""
import base64
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load(spec):
    provider = spec.get('provider', 'file')
    if provider == 'file':
        raw = Path(spec['path']).read_bytes()
    elif provider == 'vault':
        config = spec['vault']
        url = urlsplit(config['address'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Vault requires an HTTPS address without credentials or query')
        path = config['path'].strip('/')
        if '..' in path.split('/') or '?' in path or '#' in path:
            raise ValueError('invalid Vault KV v2 path')
        headers = {'X-Vault-Token': Path(config['tokenFile']).read_text().strip()}
        if config.get('namespace'):
            headers['X-Vault-Namespace'] = config['namespace']
        request = Request(config['address'].rstrip('/')+'/v1/'+path, headers=headers)
        try:
            with build_opener(NoRedirect()).open(request, timeout=30) as response:
                data = json.load(response)
            raw = base64.b64decode(data['data']['data'][config.get('field','recipient')], validate=True)
        except Exception:
            raise RuntimeError('Vault key resolution failed; response withheld') from None
    elif provider == 'kms':
        import boto3
        config = spec['kms']
        try:
            result = boto3.client('kms', region_name=config.get('region')).decrypt(
                KeyId=config['keyId'], CiphertextBlob=Path(config['ciphertextFile']).read_bytes(),
                EncryptionContext=config.get('encryptionContext', {}))
            raw = result['Plaintext']
        except Exception:
            raise RuntimeError('KMS key resolution failed; response withheld') from None
    else:
        raise ValueError('unknown recipient key provider')
    if len(raw) != 32:
        raise ValueError('recipient key must contain exactly 32 raw X25519 bytes')
    return X25519PrivateKey.from_private_bytes(raw)
