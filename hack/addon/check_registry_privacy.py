"""Actions preflight: existing public GHCR packages must never receive these builds."""
import os
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

name = 'mnemosyne-' + os.environ['TARGET']
request = Request('https://api.github.com/users/tym83/packages/container/'+name,
                  headers={'Authorization': 'Bearer '+os.environ['GH_TOKEN'],
                           'Accept':'application/vnd.github+json'})
try:
    with urlopen(request, timeout=30) as response:
        package = json.load(response)
except HTTPError as exc:
    if exc.code != 404:
        raise RuntimeError(f'GHCR privacy check failed: HTTP {exc.code}') from None
    # New GHCR packages default to private. Never change their visibility.
else:
    if package['visibility'] != 'private':
        raise RuntimeError('refusing to publish to a non-private package')
