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
uv run python -m scheherazade.weave.nocturne
uv run python -m scheherazade.weave.nocturne --decode out/works/music/nocturne/p02_000.backup.musicxml
# Encode another frame into a compatible work; keep the same key/envelope:
uv run python -m scheherazade.weave.nocturne --xml another.xml --output another.backup.musicxml --index 1
# Only a complete set may produce recovered plaintext:
uv run python -m scheherazade.weave.nocturne --decode work1.musicxml work2.musicxml --recovered restored.json
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
