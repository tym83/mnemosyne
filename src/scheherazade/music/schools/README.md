# Deterministic composition schools (grammar version 1)

Each module exposes `compose(plan: dict, seed: int) -> music21.stream.Score`.
These are explicitly limited rule systems inspired by compositional techniques,
not models of the named composers or assessments of artistic quality. They do
not call an LLM. A local Python `random.Random(seed)` owns all choices. Retain
the plan, seed, grammar source/version and Python/music21 versions for replay.
No backup payload codec is claimed: `weave/` is left untouched.

## Plan contract

See `plans/*.json` for four complete examples. `duration` and each form section's
`duration` are seconds; `tempo` is quarter notes per minute. Section durations
sum exactly to the whole. Durations must land on a sixteenth-note grid and each
section must have at least four quarter notes. There is no hidden rounding.

`ensemble`: `piano` (two staves), `string_quartet`, `chamber` (flute, B-flat
clarinet, violin, cello, piano), `string_orchestra` (10 individually notated
string lines, 4/2/2/2), `satb`. Pitches and `register: [low, high]` are **sounding
MIDI pitches**, C4=60. The intersection of register and each instrument's
practical range must span an octave. The conservative ranges are in `common.py`.
MusicXML transposes clarinet and double bass for the player; MIDI stays sounding.

`form` is an ordered list of sections, each with `duration`, `character`,
`density` in (0,1], and `register`. Characters are `still`, `flowing`, `agitated`,
`luminous`, `dissolving`; they set dynamics, and flowing/luminous stochastic
sections use glissando masses. Density changes attack spacing, not velocity.
Optional `tonic` is a MIDI tonic (default C), used by the tintinnabuli grammar
with the natural minor mode. `title`, `school` and integer `seed` are required
by the example render CLI; only musical fields matter to `compose`.

- Tintinnabuli: stepwise diatonic M walks around a centre, T lines constrained
  to a minor tonic triad, alternating nearest above/below positions and breaths.
  Piano T voice is an octave below the M centre.
- Stochastic: union of modular sieves, exponential inter-arrival times from a
  Poisson process, quantized to sixteenths with monophonic dead time. Quantization
  and minimum gaps mean the final process is not mathematically pure Poisson.
  String glissandi use continuous MIDI pitch bends, not just printed signs.
- Micropolyphony: a shared bounded chromatic walk in delayed canons at four
  speeds, close registers and a four-semitone gradual drift in each section.
- Serial: seeded twelve-tone permutation with P/I/R/RI, complete aggregates,
  mirrored timbral ordering, alternating short articulations and silence.

## Rendering and reproducibility

Run `bash hack/workshop/render_schools.sh` from the repository. Only `studio-0`
on ws1 in `tenant-scheherazade` is used. Requirements already installed in the
studio: music21/numpy, ffmpeg, FluidSynth, LilyPond and musicxml2ly. Samples are
cached in `/work/samples/vsco-schools`; works in `/work/gen/schools`, then copied
to `out/works/music/schools`. The script preserves attempts, including failed
ones. A completed destination is immutable; choose another output directory
for a changed plan. Do not mistake a repeated fetch for a new composition.

`sample_bank.py` pins VSCO CE's SFZ revision, keeps its key/velocity mappings,
uses the first round-robin take, downmixes to mono PCM and produces SF2 for
FluidSynth. Edge zones are extended to the declared instrument ranges; source
zones and per-sample SHA-256 are in `samples.json`. This is a limited conversion:
Region gain is applied with peak protection (recorded in the manifest); SFZ
modulation is not reproduced, no new sustain loops are made,
and the orchestra uses section samples for violins/violas/cellos. It is not a
replacement for a full SFZ player. No Salamander samples are used by this
profile; its verified licence is recorded as an optional future alternative.

All four supplied examples use VSCO. SATB selects an explicit FluidR3 GM
voice profile (program 53), because VSCO has no choir. Its MIT licence notice
and SF2 checksum accompany that render. Install `fluid-soundfont-gm` for SATB.
The existing NotaGen FluidR3 rendering path remains available.

Each work includes MusicXML, LilyPond source/PDF, performance MIDI, MP3, plan,
analysis, licences, sample provenance, hashes and render logs. Original WAVs
and conversion attempts stay in `.drafts`. Audio is normalized to -20 LUFS
with -2 dBTP target and two seconds of release tail; duration checks distinguish
score duration from tail. Analysis checks note ranges, nonempty parts, XML
sounding-event round trip, audio RMS/peak and duration. These checks do not
replace human listening or judge musical quality.

Local checks: `uv run python -m unittest discover -s tests -p 'test_music*.py'`.
