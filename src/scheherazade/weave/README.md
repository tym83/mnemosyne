# Weave transport preflight

This is **not yet an opus backup**. There is no approved music surface grammar,
MusicXML encoder/decoder, encoded score, or encoded audio/PDF. The existing
nocturne is untouched. Do not mark it as backup on the strength of these tests.

Run from the repository root:

```sh
uv run python -m unittest discover -s tests -p test_weave.py -v
uv run python -m scheherazade.weave.music
```

`payload.py` compresses an exact byte string, generates a fresh ephemeral
X25519 key and nonce, derives a key through HKDF-SHA256, and encrypts with
ChaCha20-Poly1305. The versioned envelope includes total length and CRC32.
The header and SHA256 of caller-supplied work context are authenticated. A
bounded decompressor runs only after authentication. This is a custom proof
format, not the age wire protocol. Recipient encryption is not an owner
signature: §40.4 authorship authentication remains unimplemented. No keys
are stored by these modules.

The intended music context must be a canonical representation reconstructed
from the encoded score, covering all protected notes, rhythm and form. The
preflight uses original XML bytes only to test the transport; this is not the
future MusicXML decoder and does not prove resistance to a changed note.

`arithmetic.py` partitions an integer interval into equal subintervals at each
slot, with the product of slot radices as its exact scale. A fixed-size byte
block selects the first lattice point in its binary interval; decoding
recovers the block and validates padding. A future grammar must reconstruct
slot radices and choices from the received work alone. It must also define
framing/size recovery without out-of-band payload metadata. No cryptographic
steganographic indistinguishability is claimed for this reference codec.

`music.py` replays the synthetic shop state at 2025-07-01, selects the complete
Namespace/shop object, verifies an envelope round trip in memory and reports
size and original-score diagnostics. JSON serialization uses sorted keys,
compact separators and UTF-8. The percentage denominator is the canonical
JSON array of all non-Secret objects, not the volume of live application data.
Its hypothetical one-bit-per-non-bass-tone capacity is not an upper bound on
all possible music grammars. Reported bit rates are requirements, not achieved
music-channel rates. Repeats increase playback time, not unique capacity.

The crude style check counts crossings between staff pitch envelopes and
music21 parallel fifths/octaves between outer voices of adjacent chordified
sonorities. It does not measure inner-voice counterpoint or artistic quality.

Before implementation of the music channel, the person making artistic
decisions must specify/approve the admissible rhythmic/figuration grammar,
including density. This follows the repository AGENTS.md restriction on
implementers making artistic decisions. Rendering then needs to accept the
encoded MusicXML directly through the studio's musicxml2ly/LilyPond and
FluidSynth/ffmpeg toolchain, preserving the decoder's source score. Publication
must follow an actual MusicXML-only decode, exact byte comparison, invariant
checks, and a one-note corruption rejection.
