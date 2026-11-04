# State backup transport

`state.collect` now collects live Kubernetes API state into canonical tar.zst.
`fountain.py`, `catalogue.py` and `backup.py` encrypt once, produce authenticated
redundant work frames, replicate a JSON catalogue into each work package's
metadata and recover after loss. See [usage and limits](../state/README.md).
The following v1 musical transport remains compatible and unchanged.

# Music surface proof (v1)

The nocturne now carries one authenticated **partial envelope frame**, decoded
from MusicXML and the recipient key alone. It is not a complete state backup.
The approved grammar is implemented conservatively: LH chord voicings and
quarter/two-eighth repeated chords. Other approved figurations and ornaments
are not used; the measured capacity is not an upper bound on that grammar.

`surface.py` reconstructs quarter cells directly from MusicXML. Each cell
preserves its bass and spelled pitch-class set. Sorted options contain 2–5
notes within a tenth, MIDI 21–108, below the minimum RH pitch in the measure.
Tied, slurred, decorated, tuplet and polyphonic LH cells are not rewritten.
The melody and every other XML element remain unchanged. RH rests and changes
in chord articulation can affect the outer-voice diagnostic; no claim of
complete contrapuntal or artistic validation is made.

`arithmetic.py` uses equal integer intervals, with no floating-point coding.
Carrier notes determine options, radices and fixed block size. All choices
including padding are decoded and validated. No bytes are hidden in metadata,
lyrics, IDs, dynamics or an external score template.

`payload.py` compresses and encrypts with ephemeral X25519, HKDF-SHA256 and
ChaCha20-Poly1305, including length and CRC32. `frames.py` splits that envelope:
4-byte bundle hint, zero-based uint8 index, uint8 count, uint16 total length,
fragment, zero padding, 12-byte HMAC-SHA256 tag. Bundle hints are not security
identities; final assembly checks the envelope and its AEAD. No plaintext is
returned for missing, duplicate or mixed frames. V1 bundles require the same
fragment capacity across works (at most 255 frames / 65535 envelope bytes).

The frame MAC authenticates the entire canonical XML tree, with carrier cells
reset to canonical voicings/rhythm. It includes melody, ties, tempo, dynamics,
slurs, rests and form; whitespace is ignored. An arbitrary notation-editor
rewrite is not guaranteed to decode, even when it sounds equivalent.

**Key model:** the encoder needs the recipient private key as well as the
public key: a domain-separated HMAC key protects individual partial frames.
This is a local proof, not a public-key-only publishing interface. Keys are
never placed in a score. The CLI creates a separate mode-0600 key, reuses it
on subsequent runs and keeps the encrypted envelope for future works. This
is not age format, an owner signature (§40.4), or a proof of steganographic
indistinguishability. PDF/audio are renditions, not supported decoder inputs.

```sh
uv run python -m unittest discover -s tests -p 'test_weave*.py' -v
uv run python -m mnemosyne.weave.nocturne
uv run python -m mnemosyne.weave.nocturne --decode out/works/music/nocturne/p02_000.backup.musicxml
# Encode another frame into a compatible work; keep the same key/envelope:
uv run python -m mnemosyne.weave.nocturne --xml another.xml --output another.backup.musicxml --index 1
# Only a complete set may produce recovered plaintext:
uv run python -m mnemosyne.weave.nocturne --decode work1.musicxml work2.musicxml --recovered restored.json
```

The final command illustrates assembly; supply all frames, not just two.
`music.py` remains the original read-only transport preflight. The default
synthetic payload is Namespace/shop at 2025-07-01, never live Secrets.

Render only in studio-0/ws1 or studio-1/ws4 with `weave.render`, which uses the
same musicxml2ly, LilyPond, FluidSynth and ffmpeg chain as
`hack/workshop/render_music.sh`, but accepts the encoded MusicXML directly.
It verifies sounding events through the engraving XML round trip, preserves
conversion warnings, and measures the resulting MP3. Keep the decoder's
original `.musicxml`; `.engraving.musicxml` is not its replacement.

## School dynamics surface (task 07)

`schools.py` encodes the authorized performance-dynamics freedom declared in
all 19 school modules. Unlike the older nocturne channel, it deliberately uses
MusicXML `sound/dynamics`: 16 levels within ±1.875 points of the written level.
Carrier IDs store only baseline/ordinal, never payload; offsets are actual
sounding positions. The exact arithmetic choice source consumes one observable
choice per knot. The entire XML context, with carrier values normalized, is
bound by a 96-bit work MAC. Glyphs retain the marked dynamic level; numeric
performance values supply its expressive shading.

API: `prepare(xml_root, school)`, `capacity(root)`, `weave_frame(root, envelope,
index, private_key)`, `read_frame(root, private_key)`. Pass recovered frames to
`frames.assemble`. For task 08, construct `fountain.Encoder(envelope,
capacity(root)-12, key)` and use `weave_fountain` / `read_fountain`, then
`fountain.recover`. Seal with the corresponding `frames.DOMAIN` or
`fountain.DOMAIN`. Series must use equal channel capacities; the encoder rejects
mismatches. Keep the existing encrypted envelope and key to add works later.

All-school measured evidence is generated by `school_audit --out NEW_DIRECTORY`.
Each plan is scaled to 180 seconds with section boundaries rounded to the
existing sixteenth grid. Reported capacity is a measured lower bound for those
plans, not an assertion about arbitrary sparse or silent works. Unsupported
short scores fail for insufficient capacity; no notes are added to inflate it.

`performance_score(path)` is the playback adapter: music21 otherwise ignores
numeric sound dynamics. The synthesis renderer interpolates its gain knots;
MIDI emits quantized CC11. Neither lossy audio nor MIDI is a decoder input.

The CLI preserves existing files and verifies every written MusicXML. The key
is created separately with mode 0600; keep it out of the work distribution.
Use the saved three-minute plan from the audit, or an explicit school plan:

```sh
uv run python -m mnemosyne.weave.school_transport \
  --plan PLAN.json --payload PAYLOAD.bin --key KEY --envelope ENVELOPE \
  --mode fountain --index 0 --out work-0.musicxml
# Repeat with new indices and output paths; reuse KEY and ENVELOPE.
# Recovery needs sufficient independent frames (the encoder reports a count):
uv run python -m mnemosyne.weave.school_transport \
  --key KEY --mode fountain --decode work-*.musicxml --out restored.bin
```

Use `--mode frames` for compact index/count frames instead. Work series may use
different musical seeds but must have equal measured capacity. Audit keys are
ephemeral and its payloads synthetic; audit XML is test evidence, not a persisted
state backup. Production CLI keys and envelopes are retained explicitly.
