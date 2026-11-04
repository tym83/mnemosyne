# Retained codecs

`v1/` contains independent copies of the initial arithmetic, Romantic MusicXML
surface, multipart, fountain and envelope algorithms. Registry adapters import
these copies, never the mutable composer or the current `weave.surface`.
Do not change a released alphabet, context canonicalization or wire format in
place. Add another version and keep the old implementation and its tests.
Security fixes must retain valid old encodings or explicitly document rejection.

`registry.DECODERS` is keyed by `(school, method, code_version)`. Each new encoded
MusicXML contains a `mnemosyne.decoder` miscellaneous field with JSON string
fields `school`, `method`, `version`. This identifies code, not frame content;
frame bytes are carried by the registered note or performance-dynamics channel.
The descriptor and other noncarrier XML are bound by the music frame MAC. No code or module names from a work are executed.
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
each, at most 255 distinct frames (1530 envelope bytes).

Following the explicit decision to allow bounded micro-dynamics, the additional
identity `romantic / nocturne-dynamics-fountain / 2` uses the retained school v2
decoder unchanged: 16 values at 0.25-point spacing, within ±1.875 points of each
baseline. `nocturne_dynamics.prepare` follows written dynamics and hairpins,
adds half-quarter sound knots on sounding spans, and preserves all original
notes, rests and notation. Hairpins without an endpoint dynamic use a 12-point
step, retained until the next written dynamic. Staff and knot positions and
baselines are authenticated with the entire musical context. Original v1 works
keep their original decoders.

`hack/restore/extend_nocturne.py` copies a prior series into a new directory,
appends one nocturne frame from the same snapshot, and verifies the unchanged
original XML tree (ignoring serialization whitespace). `music_e2e.py loss`
checks every whole-work loss combination; `apply` uses an explicitly selected
fresh test API. `render_nocturne.py` creates a piano listening preview with
continuous per-staff dynamics from the woven XML and shared tempo across staves.

## Mnemosyne rename compatibility

New works use `mnemosyne.decoder` and `mnemosyne.catalogue`. The decoder registry
accepts `scheherazade.decoder` as an alias without modifying the authenticated
XML context. Two descriptors, including one of each spelling, are rejected.
Catalogue fields are noncarrier metadata; old fields remain part of the original
authenticated context and need no rewriting for recovery.

Released v1/v2 wire domains retain their original bytes:
`scheherazade/fountain/v1`, `scheherazade/multipart/v1`,
`scheherazade/school-dynamics/v1`, and `scheherazade/school-series/v2\0`.
These are protocol compatibility identifiers, not project branding. Changing
one in place would break authentication and recovery of existing works.

New CRDs and objects use `mnemosyne.art/v1alpha1`. The atelier reader's
`GROUP_ALIASES` also recognizes `art.scheherazade.dev`; lineage restoration uses
this registry. Archive recovery preserves original API groups, namespaces,
CRDs and owner references verbatim. Reading a backup does not migrate its API.
Existing generated works in `out/` must not be renamed or rewritten.

The workshop tenant `scheherazade` and namespace `tenant-scheherazade` stay as
provisioned. Workshop scripts retain `/work/src/src/scheherazade` and the
composer's isolated `/work/composer/<run>/src/scheherazade` paths, with a sibling
`mnemosyne` import symlink. These compatibility links are created when scripts
run; the repository rename itself does not change anything in the pods.
