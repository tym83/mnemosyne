# Retained codecs

`v1/` contains independent copies of the initial arithmetic, Romantic MusicXML
surface, multipart, fountain and envelope algorithms. Registry adapters import
these copies, never the mutable composer or the current `weave.surface`.
Do not change a released alphabet, context canonicalization or wire format in
place. Add another version and keep the old implementation and its tests.
Security fixes must retain valid old encodings or explicitly document rejection.

`registry.DECODERS` is keyed by `(school, method, code_version)`. Each new encoded
MusicXML contains a `scheherazade.decoder` miscellaneous field with JSON string
fields `school`, `method`, `version`. This identifies code, not frame content;
frame bytes are carried by notes. The descriptor and other noncarrier XML are
bound by the music frame MAC. No code or module names from a work are executed.
Other arts can add explicitly registered adapters and their own input readers.

Registered identities:

* `romantic / nocturne / 1`: original multipart protocol. Unmarked old XML is
  attempted with this decoder for compatibility; its MAC must verify.
* `romantic / nocturne-fountain / 1`: the same approved note alphabet, carrying
  SHF1 plus a 4-byte length and a 32-byte context MAC. Minimum capacity is 125
  bytes. `registry.encode_fountain` checks capacity and never overwrites output.

* Each of the 19 named schools: `dynamics-fountain / 1` and
  `dynamics-multipart / 1`, using the retained `v1/schools.py` numeric dynamics
  alphabet and context. Unmarked task-17 dynamics works are also authenticated
  with these retained decoders. New CLI output includes the explicit descriptor.
* Each school: `dynamics-fountain / 2`, retaining the same musical alphabet.
  The decoded channel contains two big-endian uint32 values (frame byte size,
  count), followed by equal-size SHF1 frames, zero padding, and a 12-byte work
  MAC. The MAC binds the complete context, header, frames and padding with domain
  `scheherazade/school-series/v2\0`. Frames must belong to one snapshot and share
  dimensions. Larger works carry more equations; work loss erases the entire
  batch. `restore` combines authenticated batches with single-frame SHF1 works.

The existing nocturne's original note channel still holds 26 bytes and cannot
carry the Romantic fountain adapter. Its legacy frames hold 6 envelope bytes
each, at most 255 distinct frames (1530 envelope bytes). Extending its musical
surface requires the person's decision. The school registry does not silently
relabel a nocturne or change its approved alphabet.
