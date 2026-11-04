# Concept-first symphony, engine v1

`symphony.py` is separate from the legacy candidate concatenation in `assemble.py`.
It accepts 3–5 movements, 20–45 minutes, a concept, method, shared themes and an
explicit section plan. `plans/symphony-test.json` is the authorized test concept:
**Memory of distance**, 6 + 7 + 7 minutes. Its synthetic Namespace payload is a
public test fixture, not a real cluster backup or private information.

```sh
uv run python -m unittest discover -s tests -p test_symphony.py -v
SYMPHONY_RUN=symphony-test-v3 SYMPHONY_OUT=out/works/music/symphony/test-v3 \
  bash hack/workshop/render_symphony.sh
```

All composition, engraving and audio run at low priority in studio-0/ws1.
Use a new run/output directory for each revision. Existing works and all studio
`.drafts` are preserved. The script requires the task-14 native bank, sfizz,
LilyPond, ffmpeg, pdfunite and Python cryptography. The final transfer verifies
SHA-256 for each archive chunk and every published artifact.

## Contract

See `FORMS` for the required ordered section roles: sonata, scherzo–trio,
variations, passacaglia, rondo, through-composed, arch, moment form. These are
finite compositional scaffolds, not a claim of historical authenticity.
Sections contain whole `bars` of 4/4, a theme, transformation, centre shift and
a pair of tension values (linear interpolation). Tempo is quarter BPM, constant
within each movement. Section proportions and global duration are derived;
there is no timing rounding. `study=True` permits short unit-test plans only.

Themes specify sounding MIDI pitches and quarter durations. Identity, inversion,
retrograde, augmentation, diminution and fragmentation act on the cell;
reharmonisation changes the roots underneath its retained contour. Returns
alternate with fragmented/inverted sequences, then a two-bar centre transition.
Passacaglia retains a four-bar ground; other forms schedule contrast and return
through their explicit role/centre/transformation plans. `sections` own the
material changes, not a post-hoc concatenator. Multiple cells can be declared.
A single theme must occur in every movement. Each movement needs development.

Every school in `schools.SCHOOLS` can supply a reservoir via its actual `compose`
function. The complete source plan, seed and attacks are archived. Requirements
such as polystylism's quotation must be supplied in `school_settings`. This is
**material extraction**, not faithful transfer of a school's whole texture,
continuous bends, microtiming or extended techniques. Mixtures alternate their
reservoirs against the persistent cyclic material. The test uses tintinnabuli,
Feldman and additive reservoirs and an explicitly edited diatonic main cell.

For NotaGen, generate candidates with `notagen_batch.py`; call `selected_theme`
with the candidates directory, a `select.MOVEMENTS` criterion and tension curve.
It invokes the existing analyzer and selector, and retains candidate criticism,
selected ABC and hash. Put the result in `notagen_material` and use
`schools: ["notagen"]` (alone or mixed with rule-school names). The retained ABC
and candidate metadata record the period style; no invented model call occurs
inside the form engine. An artist can supply either type of material later.

Explicit Lines/Events go through task 14's `orchestrate`: instrument range,
sample coverage, polyphony, breathing, section balance and native SFZ playback.
The default full classical orchestra has paired winds, four horns, two trumpets,
two trombones, tuba, timpani, cymbals, harp and 16/14/12/10/8 strings. Player parts
are separate from section-part copies. Quiet passages intentionally rest brass.

## Backup and recovery

`weave.orchestral` implements one bit per harp quarter cell: ascending or
 descending octave eighths. Pitch class, beat duration, main theme and bass
remain fixed. Slots and options are reconstructed from **actual sounding
MusicXML notes**, not metadata or a sidecar. Arithmetic coding fills all slots;
X25519/ChaCha20-Poly1305 authenticates the compressed envelope against canonical
part order, pitches, durations and tempo. Engraving metadata and dynamics are
outside this version's authentication context. The complete envelope must fit;
insufficient capacity fails rather than truncating data.

```sh
uv run python -m mnemosyne.weave.orchestral \
  out/works/music/symphony/test/score.musicxml \
  --public-test-fixture --out /tmp/symphony-recovered.json
```

Alternatively give mv1/score.musicxml, mv2/score.musicxml, mv3/score.musicxml in
that order. For private data, the producer needs `--payload FILE` and
`--recipient-public-key FILE` (32 raw bytes); the decoder needs the matching
external `--recipient-key FILE`. Recipient private keys are never archived by
production. The public demo key is reproducible by design and provides **no
confidentiality**. PDF and audio are renditions, not supported decoding inputs.
Capacity is small, reported as exact bytes; no full cluster recovery is claimed.

## Evidence and limits

The work includes plan, section proportions, exact requested theme attacks and
transformations, orchestration decisions, source material, full/individual
scores, player PDFs, MP3, MIDI per movement, sample licences and checksums.
`mv*-development.json` records section usage (attacks and sounding quarters),
velocity mean/peak and source reservoirs. `analysis.json` includes measured
native-render audio peaks, RMS and loudness; velocities are a tension proxy,
not a measurement of perceived drama. MusicXML round trips and backup recovery
are checked after publication. A whole-work manifest is written last.

Weaknesses of this test are explicit: regular sequence lengths, a narrow harmonic
vocabulary, persistent harp figuration and sparse middle textures. Four-second
render tails remain between movements. Formal labels and numerical checks do
not establish artistic quality; listening and judgment remain with the person.

If engraving/audio succeeded but final publication was interrupted, retain the
same movements and their woven surface and finish without recomposition:

```sh
kubectl --kubeconfig ~/workshop.txt --context admin@workshop -n tenant-scheherazade \
  exec studio-0 -- env PYTHONPATH=/work/src/src /work/venv/bin/python \
  -m mnemosyne.music.symphony --finish /work/gen/symphony-test-v2
uv run python hack/workshop/fetch_symphony.py --run symphony-test-v2 \
  --out out/works/music/symphony/test
```

The finalizer verifies every movement manifest, MusicXML backup recovery,
combined score context, measured audio duration and actual RMS per section
before creating the complete work manifest. A published work cannot be finalized
again. The canonical weave context merges ties and restores 4/4 boundaries, so
notation-only subdivisions of compound notes/rests do not invalidate recovery.
