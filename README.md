# Mnemosyne

Memory gives birth to the arts: the cluster's backup lives in its works.
Mnemosyne is the goddess of memory and mother of the Muses.

The distribution is `mnemosyne-art`; the Python import package is `mnemosyne`.

```sh
uv sync --locked
uv run mnemo restore --help
uv run python -m mnemosyne restore --help
uv run python -m mnemosyne.restore --help
uv run python -m unittest discover -s tests -q
```

See [AGENTS.md](AGENTS.md) for project layout and workshop boundaries and
[decoder compatibility](src/mnemosyne/weave/codecs/README.md) for retained formats.
