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

There are no decoders for the existing school pieces. Do not label an unrelated
carrier as a school codec. The existing nocturne holds 26 bytes and cannot carry
this fountain adapter. Its legacy frames hold 6 envelope bytes each, at most
255 distinct frames (1530 envelope bytes). This is insufficient for the current
shop archive. A new musical alphabet or a multi-work coding scheme needs the
person's decision; the registry itself cannot supply missing artistic capacity.
