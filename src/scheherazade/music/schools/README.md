# Deterministic composition schools (grammar version 2; version 1 compatible)

Each module exposes `compose(plan: dict, seed: int) -> music21.stream.Score`.
These are explicitly limited rule systems inspired by compositional techniques,
not models of the named composers or assessments of artistic quality. They do
not call an LLM. A local Python `random.Random(seed)` owns all choices. Retain
the plan, seed, grammar source/version and Python/music21 versions for replay.
No backup payload codec is claimed: `weave/` is left untouched.

## Plan contract

See `plans/*.json` for nineteen complete examples. `duration` and each form section's
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

The four original examples use VSCO. SATB selects an explicit FluidR3 GM
voice profile (program 53), because VSCO has no choir. Its MIT licence notice
and SF2 checksum accompany that render. Install `fluid-soundfont-gm` for SATB.
The existing NotaGen FluidR3 rendering path remains available.

Each work includes MusicXML, LilyPond source/PDF, performance MIDI, MP3, plan,
analysis, licences, sample provenance, hashes and render logs. Original WAVs
and conversion attempts stay in `.drafts`. Renderer v2 used -20 LUFS normalization; v3 uses constant gain to preserve
dynamic contrasts, with two seconds of release tail; duration checks distinguish
score duration from tail. Analysis checks note ranges, nonempty parts, XML
sounding-event round trip, audio RMS/peak and duration. These checks do not
replace human listening or judge musical quality.

Local checks: `uv run python -m unittest discover -s tests -p 'test_music*.py'`.

## Fifteen additional method studies (grammar version 2)

The new plans are 180–248 seconds, with existing ensembles plus `pulse` (four
independent piano parts) and `strings_piano` (violin, viola, cello, piano).
These are technical method studies, not new artistic ideas or evaluations.
All plans preserve section/register constraints from version 1. Composers
accept an explicit seed, never call an artist, and use the existing score,
range checking, sample bank and render pipeline.

- `feldman`: five unequal durations, asymmetric returns, a single displaced
  duration and occasional semitone alteration; ppp throughout.
- `process`: identical eight-note cycles run at slightly different rates;
  later sections reveal additional positions and replace repeated pitches.
- `additive`: a 2–3–4–5–4–3 cell-length cycle above slowly changing roots.
- `in_c`: eight newly generated shared modules; independent repetitions,
  advancement bounded to two modules ahead of the slowest player. The fixed
  duration ends the realization; it does not force every player to finish.
- `spectral`: partial number determines pitch, interpolating harmonic and
  power-stretched inharmonic spectra; nearest quarter-tone orchestration.
- `sonorism`: dense quarter-tone bands, continuous bent fields, changes among
  bright bowed, percussive and noisy synthetic string approximations.
- `messiaen`: mode II, a palindromic rhythm with a central added value,
  short wide bird figures, and mode-derived piano chord colours.
- `ustvolskaya`: reiterated six-note piano clusters with hammered instrumental
  blocks; ppp unisons separate fff blocks.
- `chance`: independent six-line, three-coin parity operations determine pitch,
  duration, silence and dynamics. This is a 64-outcome oracle, not a claim
  to reproduce historical I Ching procedures. Each key has fixed synthetic
  metal resonances, short attack noise and damping.
- `tempo_canon`: a shared cell at 1:√2:√3:φ speeds; acceleration is integrated
  analytically before rounding absolute onsets to 1/32 quarter (at q=60,
  maximum error 15.625 ms, with no cumulative rounding drift).
- `aleatoric_counterpoint`: conducted outer sections and an inner section of
  independent cyclic cells. The score/audio document one seeded realization,
  not interactive live cueing.
- `fibonacci`: supplied plan durations 16:24:40:64:104 seconds (2:3:5:8:13),
  Fibonacci versus Lucas rhythms and diatonic versus chromatic pitch sets.
- `polystylism`: eight quarters of the upper voice from the atelier's generated
  Romantic nocturne `/work/gen/nocturne/rendered/p02_000.engraving.musicxml`.
  The plan embeds the complete source XML, SHA-256, original prompt and seed,
  plus extracted events; rendering requires no external quotation file.
  This is generated style-quotation, not a quotation from a Chopin score.
- `scelsi`: one centre, ±50-cent inflections, changing dynamics and additive
  timbral brightness. No melodic sequence beyond this pitch neighbourhood.
- `drone`: sustained just partials enter from low to high. `fundamental` is a
  sounding MIDI value; octave displacement fits instrumental ranges. Exact
  cents are retained as performance metadata through tied notes. Written
  notes round to quarter-tones and explicitly give the remaining cent offset.

Optional fields: `fundamental` for spectra/drones, `centre` for Scelsi,
`quotation` (required for polystylism; embedded source and event list), and
`audio_profile: "technique_synthesis"` for the four supplied sonorism/chance/
Scelsi/drone plans. Other supplied plans use the free VSCO sample bank.

### Playback and notation limits

The common event writer now supports chords and quarter-tones. MIDI uses one
channel per part, skips percussion channel 10, declares a ±12-semitone bend
range, and resets bends before every new attack. Simultaneous chord notes must
share a bend; incompatible chord bends fail explicitly. At most 15 independent
parts are supported. Irrational timing cannot be exact in finite MIDI.

MusicXML and LilyPond retain quarter-tone accidentals. Enharmonic half-flat
spellings avoid music21's loss of three-quarter-sharps during transposing
instrument export. The timing grid divides MusicXML's 10080 ticks exactly.
Proportional/graphic notation is represented honestly as measured 4/4 time
with technique/field instructions; free graphic spacing and live conductor
cues are not reproduced. The very fine measured tempo canons can be visually
dense. Just tuning is explicit in MIDI/audio; XML alone preserves the rounded
pitch plus a cents instruction, not the exact playback frequency.

`synthesis.py` creates original procedural waveforms (CC0-1.0; notice travels
with every synthetic render). Prepared-piano and extended-string techniques
are approximations, not acoustic samples; MIDI preview uses ordinary GM
instruments and does not reproduce these synthetic timbres. Sustained drones
use oscillator synthesis to avoid sample decay. The sample renders continue
to archive VSCO licence text, per-sample provenance and checksums.

Renderer version 3 uses a single constant gain per piece, preserving dynamic
contrasts instead of time-varying loudness normalization. Absolute loudness
across different pieces is not comparable. Every audio file retains planned
silence and a two-second tail. Technical checks are not listening approval.

Render selected schools with `bash hack/workshop/render_schools.sh feldman
process ...` (or omit arguments for all 19). Finished work is never overwritten;
all attempts are retained in the pod. Published artifacts transfer through a
verified staging archive with retries; raw WAVs remain in the pod. After all files arrive:

```
uv run python -m scheherazade.music.schools.catalog out/works/music/schools
uv run python -m unittest discover -s tests -p 'test_music*.py'
```

The catalog checks every published artifact hash before writing `INDEX.md`.
