# Deterministic composition schools (grammar version 2; version 1 compatible)

Each module exposes `compose(plan: dict, seed: int) -> music21.stream.Score`.
These are explicitly limited rule systems inspired by compositional techniques,
not models of the named composers or assessments of artistic quality. They do
not call an LLM. By default an unmodified Python `random.Random(seed)` owns all choices. Retain
the plan, seed, grammar source/version and Python/music21 versions for replay.
Every composer also accepts keyword-only `choices: ChoiceSource | None` (see
`choices.py`). A supplied source owns all grammar draws and supersedes the seed;
the caller owns its state. Omitting it preserves the previous seeded output.
The original grammar draws alone are not invertible: some outcomes are discarded.
The approved surface expansion is separate from those draws. Every school now
states `FREE_CHANNELS` beside its rules. `weave.schools.ArithmeticChoices` drives
16 small performance-dynamics variants around the existing marked level,
at sounding onsets and half-quarter knots inside sustained notation. No pitch,
rest, rhythmic proportion, row order or technique is changed by this channel.
The remaining authorized freedoms (microtonal contours, bowing, entry order,
etc.) are not required for the measured target and are not silently rewritten.

`weave.school_audit` measures all twenty-eight schools after actual XML serialization,
checks pitch/duration invariants and tamper rejection, compares woven/unwoven
histograms and recovers both compact frame series and task-08 fountain series.
Run the full audit in a studio:

```sh
python -m mnemosyne.weave.school_audit --out /work/gen/school-weave-RUN
```

Its `CAPACITY.md` contains measured three-minute capacities, net frame data and
statistics. `school_capacity.py` retains the historical raw-grammar support
functions for regression tests; these are not capacities of the new surface.
`weave.schools.performance_score(path)` preserves the numeric performance knots
when importing into the atelier: music21 alone ignores `sound/dynamics`.
Synthesis interpolates gain continuously; the MIDI adapter emits CC11 (quantized).
Only original MusicXML is a supported backup decoder input.

Solo S/A/T/B remain available for notation, unavailable for sampled audio.
Vocal realizations use the explicit choir instruments. Sonorism and chance
use the authorized procedural profile with `sound_origin: synthesized` and the
same measured hall as the sample renderer; no choir or sustain patch substitutes
for a missing solo voice or extended technique.

## Plan contract

See `plans/*.json` for twenty-eight complete examples. `duration` and each form section's
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
process ...` (or omit arguments for all 28). Finished work is never overwritten;
all attempts are retained in the pod. Published artifacts transfer through a
verified staging archive with retries; raw WAVs remain in the pod. After all files arrive:

```
uv run python -m mnemosyne.music.schools.catalog out/works/music/schools
uv run python -m unittest discover -s tests -p 'test_music*.py'
```

The catalog checks every published artifact hash before writing `INDEX.md`.

## Nine older traditions (grammar version 2)

The founding schools are all twentieth-century methods. These nine add older
techniques with the same plan contract, `FREE_CHANNELS`, poetics in
`atlas/music/poetics/` and example plans of 180 seconds. They are limited rule
systems inspired by techniques, not models of the named composers; no surviving
melody is quoted. Shared helpers: `chant.py` (eight church modes, stepwise
degree walks, tenor/upper voice roles) and `tonal.py` (keys, numerals including
applied chords, ensemble roles).

- `ancient_greek`: two disjunct tetrachords in the diatonic, chromatic or
  enharmonic genus (quarter tones, sounding pitches x.5; still/dissolving
  sections are enharmonic), an octave species chosen by seed, lines of
  long/short feet ending on a triseme; heterophonic aulos and lyre parts.
  Piano plays only the fixed (semitone) notes.
- `gregorian`: one of eight modes (final, reciting tone, ambitus); psalm-tone
  recitation, neumatic groups of 1-3 eighths or melismas by section; cantor and
  choir alternate in unison/octaves over an ison on the final (an Eastern
  practice borrowed here, documented in the poetics).
- `organum`: chant tenor in the lowest non-piano part, held 4-8 perfections
  (discant longs in dense sections); up to three upper voices in rhythmic modes
  I, II, III or VI, with a unison, fifth or octave above the tenor on every
  perfection and stepwise passing notes between.
- `ars_nova`: tenor from a talea (3-5 values and a rest) and a color whose length
  is not a multiple of it; diminution in agitated sections, an isorhythmic
  contratenor, hocket in dense sections, double-leading-tone cadences.
- `renaissance_polyphony`: points of imitation with equal entry distances on
  the final and the answer interval (least-clash choice), consonance-checked
  free counterpoint, 7-6 suspension cadences on the final (musica ficta except
  Phrygian). Parallel perfect intervals are not checked.
- `fugue`: two-bar subject, real/tonal answer at the fifth, one recurring
  countersubject, sequential episodes on the subject head, middle entries in
  related keys, stretto, dominant pedal and a Picardy close.
- `basso_continuo`: ritornello (tutti, f) and circle-of-fifths episodes (solo,
  p); the bass moves on every beat, the keyboard realizes chords above it. The
  plan's section dynamics are replaced by these terraces.
- `classical`: parallel periods (half cadence, then ii-V7-I) with Alberti or
  pulsing accompaniment; middle sections in the dominant, a modulating
  consequent and a retransition on the home V7.
- `romantic`: long melody with opening leaps and appoggiaturas over wide
  arpeggios; applied dominants, diminished sevenths, a chromatic-mediant middle
  key, suspensions, phrase swells and one climax that widens the register.

`tests/test_old_schools.py` checks each signature device on the example plans.

## Shared instrumentarium and native SFZ rendering

The old SF2 profile above remains for replay of archived works. New realizations
use `audio_profile: "native_sfz"`. `music/instruments.yaml` separates sounding
instrument ranges, comfortable ranges, written transposition, clefs, practical
velocity bounds, phrasing, seating, and **actual sampled key ranges**. A real
instrument's range is not a promise that its sample patch covers that range.
Velocity bounds and balance are configurable heuristics, not measured physical
limits. `music/ensembles.yaml` defines the named ensembles, player counts and
section divisions; the version-2 material voice counts are retained separately
as `legacy_voices`. A quartet now uses four solo sample instruments, including
solo viola and cello. Five section identities are separate from the solo strings.

A school plan retains its `ensemble` for the existing grammar's material voices
and adds `orchestration`, either a named ensemble or a list such as:

```json
[
  {"instrument": "flute", "count": 2},
  {"instrument": "horn", "count": 2},
  {"instrument": "violin_1_section", "players": 8, "divisi": 2},
  {"instrument": "cello_section", "players": 4, "divisi": 2}
]
```

For new non-school compositions, `orchestration.orchestrate(lines, plan)` accepts
`Line`/`Event` objects directly; `ensemble` itself can then be a custom list.
Roles are `melody`, `bass`, `harmony_pad`, `counter_line`, `figuration`,
`cluster_field`, and `percussion_layer`. Register and event pitches are sounding
MIDI; onset/duration are quarter notes. Lines carry density, colour and optional
mandatory instrument. Stable assignment considers range, sample coverage,
colour (`dark`, `glassy`, `brassy`, `woody`), role and available players. Chords
split across divisi when no eligible polyphonic instrument can play them.
An impossible assignment raises an error, rather than dropping notes or changing
pitch. `doublings: true` permits loud melody/bass unisons on available players.
Winds get actual breathing rests; long strings get bow-change attacks. Every
assignment, dynamic clamp and breath is recorded in `orchestration.json`.

`line_roles`, `line_colours` and `line_instruments` are optional dictionaries
indexed by the material voice number as a string. They override the adapter's
inference. This layer is a feasibility heuristic, not an autonomous artistic
orchestrator. The school algorithms still own their rhythms and pitch processes;
the adapter preserves their pitches, dynamics and glissandi before assigning
playable parts. `orchestrated_plans/` contains separate revised realizations of
the nineteen founding studies and of the nine older traditions (choir for
chant, organum, ars nova and Renaissance polyphony, with the register raised to
the choir samples; string orchestra for the fugue; strings and harpsichord for
basso continuo; string quartet for the classical school; symphony orchestra for
the romantic one); the original plans and published works are preserved.
The narrow Ligeti registers are explicitly permitted by that grammar. Xenakis
uses wide registral mass and ff/fff, Webern is a 24-second sparse point study,
and Pärt uses a bell/strings ensemble and stillness. Other profiles follow the
methods already documented above. They remain technical studies, not claims
of artistic authenticity.

### Native sample and audio path

`music.sample_bank --native` delegates to `native_bank`; the old eight-preset
conversion is no longer used by this profile. Pinned Sonatina SFZ, Shinyguitar,
FreePats Button Accordion and a VCSL dan tranh subset retain stereo, velocity
layers, loops and all round-robin takes. Native source files remain unchanged.
Working SFZ copies resolve historical filename-case differences and paths,
convert uniform random take selection into deterministic round-robin cycling,
and declare a ±12-semitone pitch wheel range. These working copies travel with
the work. SFZ playback uses sfizz 1.2.3, not a partial home-made synthesizer.
Some upstream patches derive harmonics/legato from transformed samples; the
library's README documents that. A patch is not evidence of separately recorded
extended techniques.

Each instrument/articulation has its own stereo stem and sampler instance.
Consequently audio is independent of MIDI's 16-channel limit. Preview MIDI uses
multiple ports (15 pitched channels per port, channel 10 for percussion).
MusicXML receives corresponding port metadata. Stems are balanced and seated,
then convolved with the OpenAIR Jack Lyons Hall response (central seating D22,
B-format decoded to stereo). A measured **constant** gain targets −20 LUFS,
limited by −1.5 dBTP headroom; the report explicitly says when the loudness target
cannot be reached without reducing dynamic contrast. The complete four-second
IR tail is retained. This is not a compressor or time-varying normalization.

Full scores are transposed for players and checked by returning MusicXML to
sounding pitch. Large scores use A3/A2 paper. Each player/divisi group has an
extracted PDF; section musicians receive copies of their assigned group part.
Unpitched percussion uses percussion notation, not displayed SFZ trigger pitches.
Raw WAV stems, intermediate mixes and failed attempts stay in `.drafts` in the
studio. Published files include the plan, orchestration decisions, score, parts,
MIDI, MP3, analysis, source snapshots, normalized SFZ mappings, sample hashes,
licences, credits, and a manifest written last. Existing successful works are
verified and never overwritten.

### Availability and honest limitations

The registry currently describes 48 instruments and 21 named ensembles.
Four solo vocal types are **not sample-backed**: no verified free solo S/A/T/B
set was found. Choir samples are explicitly section instruments and are never
substituted for solo voices; `voice_and_piano` therefore fails preflight.
`dan_tranh` is the non-Western instrument currently provided; no gamelan set or
shakuhachi is claimed. The VCSL recorded pentatonic tuning is documented in its
mapping; chromatic playback transposes the nearest recording.

Unavailable techniques (including sul ponticello, bow pressure, wind
multiphonics, and muted/stopped brass in these selected patches) are declared
rather than replaced by generic sustain. `sonorism` and `chance` require an
explicit decision about retaining their former procedural realization versus
waiting for acoustic samples. Their new native runs report this limitation.
The complete upstream Sonatina README is included because it describes mixed
historical sample provenance. OpenAIR's dataset page was unavailable during
implementation; its CC BY 4.0 designation was corroborated by redistributors,
not reverified on that page. These limitations are retained in the library
manifest, not hidden behind a successful download.

### Run and verify

All audio rendering, downloads and engraving run in `studio-0` on ws1, namespace
`tenant-scheherazade`. No artist/LLM is invoked. The environment needs
`music21`, `numpy`, `pyyaml`, `ffmpeg`, `musicxml2ly`, `lilypond`, and
`/work/sfizz-build/library/bin/sfizz_render` (1.2.3).

```sh
bash hack/workshop/render_ensembles.sh
# Or selected entries; completed artifacts are checked and reused:
bash hack/workshop/render_ensembles.sh --mode demos --only wind_quintet string_quartet
uv run python -m unittest discover -s tests -p 'test_instrumentarium.py'
uv run python -m unittest discover -s tests -p 'test_music*.py'
uv run python -m mnemosyne.music.distinctness out/works/music/ensembles/schools \
  --out out/works/music/ensembles/distinctness.json
```

The render script transfers verified completed artifacts to
`out/works/music/ensembles/<ensemble>/`; school realizations are in its `schools/`
subdirectory. It also transfers failure reports and exits nonzero if any requested
entry failed, even when others succeeded. Use a new `INSTRUMENTARIUM_RUN` value
for changed inputs, and preserve existing local works by choosing a new output
location before transferring a changed realization.

`distinctness` compares completed school scores using six feature groups:
register statistics, attack density, interval classes, duration distribution,
dynamic distribution and timbre usage. It reports the ten closest pairs and
rejects exact feature duplicates. Distances are descriptive, not listening
approval and not a claim that every study sounds distinct to a person.

The existing symphony assembler also routes each selected movement through this
layer by default (`music.assemble symphony --sample-bank ...`). Its optional
`--orchestration-plan` supplies ensemble/colour/line assignments; it archives the
original movement XML and key transposition in the plan. Existing output folders
are refused. `--legacy-soundfont` explicitly selects the former renderer.
At present this adapter accepts constant-tempo movements only: a changing tempo
map is rejected rather than flattened. The four-movement assembler itself is
not an artist and does not select new musical material.

To reproduce the studio's sfizz build, run
`bash hack/workshop/prepare_instrumentarium.sh` before rendering. It installs
build dependencies and compiles the pinned 1.2.3 release in `studio-0` with two
low-priority build jobs. Its source archive remains in `/work`.

## Schools born in the atelier

`music.school_birth` lets an artist found a school that did not exist. The
composer chooses `invent_school`, writes a manifesto, then writes the grammar
itself as a Python module in the same shape as the founding schools. Admission
is mechanical, never aesthetic: a static allowlist (imports, names, no private
attributes, no classes), a trial in an isolated child interpreter with CPU and
memory limits (deterministic per seed, instrument ranges, the standard school
surface with at least 32 bytes per three minutes and an exact round trip), and
a measured distance from every existing school that must exceed half the median
nearest-neighbour distance among them. A grammar that only renames a school is
returned to the artist with the measurement. The artist's inner critic then
accepts or refuses it. Rejected attempts stay in the notebook and wound.

An accepted school lives in the lineage state (manifesto, source, plan, trial,
verdict, author, followers), so it is part of every backup. Its works decode
without its code: the surface codec is shared. Studio requests carry born
sources and re-check them before registering. Followers join through
`borrowed_method` encounters and apprenticeship. Chamber mode can compose in
born schools but cannot found one: founding needs the artist's words.
