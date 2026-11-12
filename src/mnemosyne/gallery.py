"""The gallery: the atelier's history as a site anyone may browse, read-only.

It reads the studio volume mounted read-only, rebuilds the static site into
its own scratch directory every few minutes, swaps it in whole, and serves it.
It holds no keys, no service account token and no write access to the atelier.

  python -m mnemosyne.gallery --root /works/NAME --site /site --port 8080 --every 900
"""
from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path
import shutil
import threading
import time


def build(root: Path, site: Path) -> Path:
    from .viewer import Atelier, site as export
    fresh = site.parent/f'{site.name}.next'
    shutil.rmtree(fresh, ignore_errors=True)
    export(Atelier(root), fresh)
    old = site.parent/f'{site.name}.old'
    shutil.rmtree(old, ignore_errors=True)
    if site.exists():
        site.rename(old)
    fresh.rename(site)
    shutil.rmtree(old, ignore_errors=True)
    return site


def keep_building(root: Path, site: Path, every: int):
    while True:
        try:
            if (root/'lineage.json').exists():
                build(root, site)
        except Exception as exc:  # the gallery keeps serving the last good site
            print(f'gallery: rebuild failed: {type(exc).__name__}: {exc}', flush=True)
        time.sleep(every)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


def main(argv=None):
    ap = argparse.ArgumentParser(prog='mnemosyne.gallery')
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--site', type=Path, default=Path('/site/current'))
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--every', type=int, default=900)
    a = ap.parse_args(argv)
    a.site.parent.mkdir(parents=True, exist_ok=True)
    a.site.mkdir(exist_ok=True)
    if not (a.site/'index.html').exists():
        (a.site/'index.html').write_text('<!doctype html><meta charset="utf-8"><p>Мастерская ещё собирается.</p>')
    threading.Thread(target=keep_building, args=(a.root, a.site, a.every), daemon=True).start()

    # The path is resolved on every request, so a swapped-in site is served at once.
    handler = functools.partial(Handler, directory=str(a.site))
    http.server.ThreadingHTTPServer(('', a.port), handler).serve_forever()


if __name__ == '__main__':
    main()
