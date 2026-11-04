# Restore from works

```sh
uv run python -m mnemosyne.restore --works DIR --key KEYFILE --dry-run
uv run python -m mnemosyne.restore --works DIR --key KEYFILE \
  --output out/new-restore --apply --kubeconfig K --context C
```

Every `.xml` and `.musicxml` under DIR is attempted. Unsupported, damaged and
unwoven XML are reported as rejected paths and treated as lost works. Neither
`frame.bin`, the original archive, nor an external catalogue is a restore input.
MP3/PDF/MXL are not decoder inputs. See [retained codecs](weave/codecs/README.md).

Frames are authenticated before grouping. Fountain snapshots and legacy
multipart bundles are reconstructed separately; duplicates do not add rank.
School dynamics v1 and variable-capacity v2 frame batches are supported by
retained codecs. Multiple equations in one work are lost together; redundancy
must therefore be measured over whole works, not individual frames.
Envelope AEAD is checked before reading tar.zst. Exactly one distinct complete
state archive must be recoverable; multiple complete snapshots fail rather
than choosing a date implicitly. Incomplete unrelated bundles are reported.
The historical single-Namespace JSON payload is not a state.collect archive
and is deliberately not presented as a complete cluster backup.

Archive parsing accepts regular YAML members only, validates hashed object
identities, rejects duplicate identities and Secret kinds, bounds expansion to
128 MiB, and never extracts tar paths. It does not require zstd recompression
to produce identical bytes across future library versions. Output is a new
mode-0700 directory (`out/restore-*` by default) with mode-0600 archive,
ordered `manifests.yaml`, and `report.json`; existing outputs are never replaced.

Without `--apply`, no cluster is contacted. `--dry-run`, even with `--apply`,
also makes no cluster requests: it verifies and writes the same artifacts.
An actual apply requires both explicit kubeconfig and context, uses server-side
apply with field manager `mnemosyne-restore`, and never forces conflicts.
CRDs are applied and waited for first, then namespaces, other cluster objects,
then namespaced objects. Each phase retries unresolved dependencies five times.
API discovery validates actual scope. Namespaced objects need explicit
namespaces; unknown unnamespaced kinds are ordered as cluster objects but
must pass discovery before applying. Owner references are resolved by
API version/kind/name to the new UID, with dependencies retried.

Successful applies remain if a later object fails; rerunning is idempotent.
No rollback, pruning, volume data restore, finalizer removal, Service address
remapping, or PV/PVC rebinding is performed. Existing allocated fields may be
unsuitable for a different target and cause an apply error. API defaulting can
add fields: matching source fields is weaker than exact normalized equality.
Application readiness is outside this API-object restore command.

## Checks

```sh
uv run python -m unittest discover -s tests -p test_restore.py -v
```

Heavy checks belong in a studio pod. `hack/restore/check_fixture.py` accepts
`--source shop.yaml --output NEWDIR --kubeconfig K --context C`. It embeds the
archive in synthetic note-cell fixtures, omits ceil(30%) of work slots without
deleting files, invokes the real CLI against an isolated API server, and checks
both exact normalized equality and retention of every source field. These
fixtures are not compositions and this check does not satisfy the requested
school pieces + nocturne + rendered MP3 acceptance. No artistic decision is
made by the fixture generator.

## Composer notebooks

Composer snapshots use the same state archive format. Notebook entries and
Biography chapter text are ordinary object fields, including rejected plans
and verdicts. Audio/score assets retain atelier content hashes; the object
archive does not embed the external content-addressed blob store.

For completed school nights, point `--works` at the notebook's `woven/`
directory. Each original MusicXML carries authenticated fountain frames and
an embedded catalogue of their carrier assignments. Rendered MP3/PDF and
engraving re-exports remain listening/reading formats, not decoder inputs.
`decode.json` distinguishes verified individual frames from a recovered full
archive. A `backup_pending_capacity` night cannot restore the snapshot alone.
The snapshot boundary precedes weaving and the final decode report, avoiding
self-reference; these later records are saved for the next backup.

The equivalent console command is `uv run mnemo restore …`. See
[rename compatibility](weave/codecs/README.md#mnemosyne-rename-compatibility)
for retained decoder names and API groups.
