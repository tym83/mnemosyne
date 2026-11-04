# Lineage and Lives

`lineage.Lineage` owns a nightly state machine and a private seeded RNG. It
receives only `mood(...)["qualities"]`, never incident identities. Birth of the
first artist is the scenario start. Other births fill creative vacancies.
`Parameters.spaces` limits working/ill artists to 1–3; silent people remain
alive, age, encounter others, and receive chapters. Ready returners precede
newcomers when a place opens. Death never frees or destroys archived works.

Health, creative energy, skill, maturation, openness, drive, resilience,
attachment, grief, faith, isolation, recognition, money, commercial pressure
and fertility interact. Stable solitude is set at birth from the initial isolation
(`isolation ** 4`), then retained independently of later exile. Relationship
attempts, including apprenticeship and rediscovery, require both endpoints
to engage, with probability `(1 - source.solitude) * (1 - target.solitude)`.
The global encounter rate is unchanged. No artist is assigned a trajectory label. Relationships
are directed, weighted records; their endpoints may include dead teachers.
External-atelier relations can use the same edge schema, but no cross-cluster
broker is implemented. Poverty and commercial pressure are optional through
`Parameters.money_enabled`.

Rates and lifecycle thresholds live in `Parameters`, in nights. Defaults put
maturity at 50 nights, late age at 390 and rising old-age mortality after
600. One night is one real day. The age hazard is 0.03 × (age − 600) / 365
after day 600; combined with accidents this gives a survival median near
730 nights (about two real years), before illness. Individual maturation
ranges from 25 to 500 nights; mastery requires 300 unrepeated working nights.
A five-year cluster therefore spans roughly three generations along an
occupied creative place; silence and early vacancies can add successors. A rare accidental death has probability 0.000025 per night. Illness
requires ten sustained heavy nights plus low vitality and either repeated
rejections or exhaustion below 0.2 vitality. After the 4-night onset and
8-night crisis, survivors either recover over 12 nights or enter a prolonged
illness with probability `0.5 * (1 - resilience)`. After 90 further nights,
the prolonged illness settles into a persistent changed voice: health stays
at 0.6, vitality gains 0.35, and a new method period begins. This is adaptation,
not restored health. The historical `illness_recovery` event key remains for
readers, with `altered_voice=true`, `outcome=changed_voice` and the duration;
no `recovered` event follows. Ordinary recovery does not assign an altered
voice. Silent artists become ready for a vacancy, unless they renounced work;
occupancy and ordinary mortality still apply. These are synthetic
calibration choices, not medical or historical claims. Silent people are not
removed to enforce a living-population cap.

The work stub samples a four-dimensional feature vector and compares it with
**the entire own catalogue**. Quality, novelty and the inner critic's fallible acceptance are
synthetic measurements. Rejected work remains in the notebooks and can
be rediscovered after the configured discovery age (90 nights by default). A dying artist completes a last-work
stub before its status becomes dead. No later work can be added. The notebook
records preparation, incubation, dreams, illumination and verification; an
illumination can still be refused. Fertile and fallow periods require sustained
state, rather than a calendar date.

Artistic integration boundaries:

- `Artist.problem` accepts a problem previously set by the artist;
  `Lineage.idea_seed(id)` supplies the current insight to
  `artist.statement(..., illumination=seed)`. The inner critic still questions it.
- Period changes request a theme/method; they do not invent artistic doctrine.
  `school_attempts` records requests for `artist.method(..., allow_invention=True)`.
  Synthetic runs can give an explicitly marked surrogate school verdict, without
  writing to the atlas. Real methods enter through `accept_school` after review.
- `--words` uses `Writer` solely for prose: the portrait, turning-point diary,
  illness letter, final idea, dream image, and the chronicler's chapter. It cannot
  roll fate RNG or change verdicts. One chronicler instruction is shared by the
  whole atelier; historical snapshots, linked catalogue entries, notes, previous
  chapters and diaries are supplied. Chapter interpretation may be legendary;
  structured facts remain authoritative. No `--words` call was used in validation.
- The regular art production pipeline is not automatically launched. Stubs have
  `synthetic: true`, and pending artistic content is explicitly empty.
  `step(mood, work_source=...)` accepts a producer's measured feature vector,
  novelty, quality, verdict, idea and process references, including the final
  piece. Replay then needs these recorded observations as well as mood history.
  `Parameters.synthetic_schools` defaults to false; only synthetic CLI and
  population experiments enable surrogate school acceptance.

`state()` / `restore()` preserve RNG and all history through JSON. Missing
solitude in older checkpoints defaults to zero; archived relationships and
lifespan parameters are preserved. Future nights use the retuned forces, so
continuing an older checkpoint is not a replay under the old engine.
`Atelier.lineage()` emits Artist and Biography objects, one growing literature
Opus, and resolvable Opus/Notebook/Sketch links. `Lineage.from_objects()` resumes
from those manifests. The book's Markdown file is content-addressed by the
atelier store. Biography facts and text are backed up as ordinary state.

`weave/biography.py` is the literature transport boundary: the same encrypted
payload envelope and authenticated multipart framing as other weave channels.
There is **no prose codec yet**, so verified present capacity is zero. A planning
example of 800 independently reversible binary choices gives 100 gross bytes,
80 after each frame's overhead; the envelope additionally costs 72 bytes plus
the compressed payload. This is a budget example, not a claim about natural
language capacity. A future codec must demonstrate extraction before advertising
capacity. The hook produces frames, not text with a hidden payload.

Run the synthetic year (CPU work in a studio pod):

```sh
uv run python -m mnemosyne.lineage shop bank --seed 17
```

Outputs: `out/works/lineage/{shop,bank}.{md,json}` plus atelier manifests and
content-addressed book files under `out/works/lineage/atelier/`. `--words` is
optional and calls the configured Writer backend; launch only after review in
accordance with AGENTS.md. Existing artwork is never deleted.

Contract tests: `uv run python -m unittest discover -s tests -p test_lineage.py -v`.
Population test: `python -m unittest discover -s tests -p test_lineage_population.py -v`
in the studio environment with the package on PYTHONPATH. It runs 48 independent
five-year histories and classifies the *observed* lives using work quality,
chronology, periods, relationships, silence and recognition. These labels are
never seen by the engine. The test also bounds lifespan statistics, checks that
the dead do not produce works and that creative occupancy never exceeds capacity.

## Historical validation (previous lifespan defaults)

- 10 lineage/carrier/idea-stage unit tests and 9 existing weave tests passed.
- The 48 × 20-year population test passed in `studio-0` on ws1: 490 completed
  lives, median 2658.5 nights, range 114–4302. Observed trajectory counts:
  meteor 59, late bloomer 86, craftsman 86, posthumous recognition 39,
  prodigy burnout 10, return after years 185, school with continuers and heretics 9,
  rival artists 220, renunciation 10, changed voice after illness 21,
  rediscovered 355, hermit 10. Labels can overlap; this is a fixed-seed synthetic
  regression sample, not evidence of historical realism.
- Both fertile and fallow periods, dreams, illumination, verification, mastery,
  illness phases and chapters of silence were observed.
- `mood.py` now uses strided weekly groups instead of repeated full-array masks.
  Shop and bank at days 1, 180 and 365 exactly matched the previous implementation.
- The 365-night seed-17 run gave shop: 3 artists / 19 chapter stubs; bank:
  3 artists / 22 chapter stubs. Each ended with two working artists and one
  silent artist, no deaths. JSON, restored manifests, Markdown and chapter
  references were checked for consistency. No LLM calls were made.
- The first remote attempt failed because `pydantic` was absent. Pydantic and
  PyYAML were installed under `/work/lineage-check/deps`, without modifying the
  shared virtual environment. An early population probe found no returns;
  reserving vacancies for ready returners fixed that lifecycle defect.

The long runs used `/work/venv/bin/python` with
`PYTHONPATH=/work/lineage-check/src:/work/lineage-check/deps`, only in namespace
`tenant-scheherazade`, context `admin@workshop`, kubeconfig `~/workshop.txt`.
No workloads were placed on ws2/ws3, no Secrets were read, and no artist or
Codex subprocess was launched. Changes remain uncommitted.


## Reception (engine version 2)

`Artist.inner_critic` stores atlas tests as values/aversions, pride, shame,
threshold, bias and uncertainty. Teachers and encounters shape it; changes of
life alter its threshold. Synthetic drafts retain every revision. Acceptance
is fallible; refusal retains the work. Repetition leads to silence, never death.
Version 1 checkpoints retain their archives on import; missing merit uses the old
quality estimate and new reception starts at import. Future nights use version 2
rules, so this migration is not a replay of the old fate engine.

`Reception` is shared by the atelier. Six critics have independent tastes,
school loyalties, biases, reputation and voices. Four listener segments perceive
merit through noisy preferences, fashions, reviews and word of mouth. Cumulative
listening gives preferential attachment. Attention decays to complete oblivion;
random discoveries may revive any quality, during life or after death. Editions
from notebooks are separate events: the dead never create new works. Recognition,
royalties and influence return to the fate engine. Hidden merit is diagnostic
state, never a field supplied to review writers. It is not a claim about actual art.

Review prose uses the literature hook (zero verified capacity); `write_words`
is opt-in. Audience logs use `weave.audience`: 256 sampled session timestamps
with uniform 0–255 ms jitter, one byte per session. Counts, charts, programme,
ratings and seconds are preserved. Keyed whitening masks frame structure. This
is a tested synthetic distribution, not a claim of undetectability in real logs.
Fountain overhead is 88 bytes: 256 gross / 168 envelope bytes per active night;
silent nights have zero capacity. Encryption adds 72 bytes per snapshot, plus
compression effects; redundancy and loss consume additional capacity. Reviews,
editions and logs are persisted alongside works in the atelier catalogue.

Run the ten-year experiment in studio-0 with the repository on PYTHONPATH:
`python -m mnemosyne.reception_report --seed 17 --out /work/reception/output`.
The report labels retrospective examples using explicit numerical thresholds;
it never injects those labels into fate. JSON checkpoints, full works/reviews
and sparse nightly curves accompany the report.

## Composer nights

`music.composer` connects the existing idea/interrogation stage, inner life,
teachers, own catalogue and contemporaries to a musical method, halftones,
validated plans, studio sketches, score-image/analysis criticism, revisions,
and a real `record_work` observation. Quality and significance are the
artist's verdict; the fate engine does not invent them. Novelty compares
measured descriptors only with earlier real works, excluding synthetic stubs.
A significant work adds a chronicler chapter with the same work ID.

`Atelier.lineage` retains composer processes and their Sketch objects on
re-export, including content-addressed file references. Pending/failed nights
also emit Opus and Notebook objects. A new-school request stops at a retained
`needs_grammar` hook. It does not manufacture an atlas school.

Existing checkpoints retain their recorded lifespan parameters. Checkpoints
without maturation bounds retain the former 90–1800-night birth distribution;
new default lineages use the two-year calibration. No archived life is rewritten.

Launch outside an environment that blocks nested Codex:

```sh
WRITER=codex uv run python -m mnemosyne.music.composer \
  --lineage out/works/lineage/shop.json --key out/keys/composer-shop.key
```

The input checkpoint is immutable; the updated checkpoint, notebook, studio
artifacts, atelier manifests and decoding report live beneath
`out/works/composer/<artist>/<work>/`. Use `--run-id NAME` to retain a failed
attempt and start a new directory. Music workers use only studio-0/ws1 or
studio-1/ws4 and never invoke Writer. The caller retains the private key outside
the notebook and never sends it to a pod.

School backups snapshot the atelier after the verdict and biography but before
weaving; later render/decode results belong to the next snapshot. Frames are
assigned to actual sketch/draft identities by an authenticated catalogue.
Insufficient capacity leaves `backup_pending_capacity`, a pending encrypted
envelope and explicit missing-frame count. This is not a successful full backup
or a verified 30% loss claim. Symphonic composition and criticism use the cyclic
engine. Each movement is a carrier with the same bounded local dynamics
freedom as school material; its original orchestration and tempo are retained
when rendering the woven movement. The v2 dynamics decoder also registers
`(symphony, dynamics-fountain, 2)`.

### Two-year calibration verification (2026-11-04)

The updated 48 × five-year population regression passed in studio-0:
293 completed lives, median 724 nights, range 183–951. All twelve retrospective
trajectory categories remained present, including late returns, illness with
changed voice, prodigy burnout and schools with heretics. These remain synthetic
measurements, not historical or medical claims.

The actual `WRITER=codex` attempt for shop-0001 was retained under
`out/works/composer/shop-0001/shop-0001-w00099/`. It failed at statement:0:
`failed to initialize in-process app-server client: Operation not permitted`.
No completed artistic night or full shop recovery is claimed for that attempt.
The separate existing tintinnabuli plan rendered successfully in studio-0
(60 seconds, 2 parts, no out-of-range notes), including its score-image export.

Final checks for the composer change: 7 composer orchestration contracts,
10 lineage, 7 reception, 7 restore, 6 fountain, 3 composer transport,
2 retained school-series, 11 symphony tests, and the population experiment
passed (54 checks across separate runs). The full-night contract uses test
doubles for Writer/music; it is not evidence of an actual artistic night.
The transport checks use real generated MusicXML and recover Notebook and
Biography objects without reading frame sidecars. Catalogue tampering fails
authentication. `git diff --check` and compilation passed.

Intermediate failures were retained in tool output: the isolated studio test
copy initially lacked atlas resources; a four-carrier fixture could not hold
the snapshot after CRDs were added (expanded to sixteen test carriers); a test
incorrectly assumed directory iteration returned carrier zero first (changed
to compare against the actual filename). Symphonic tests emitted music21 MIDI
channel/ID warnings but passed. These do not establish sampled rendering of a
complete artist-authored symphony or NotaGen night; that remains unverified
because the actual Writer run was blocked before composition.

## Configurable models — 2026-11-04

`Writer` now reads `MNEMOSYNE_MODELS` (YAML; see
`config/models.example.yaml`). No configuration means no model, not a developer
subscription. `WRITER` can explicitly override routing with a configured endpoint
name, `none`, or a development-only `codex`/`claude` backend. The former implicit
`api` backend is replaced by an explicitly named Anthropic endpoint and model.

Roles are `artist`, `critic`, `chronicler`, and `eye`; each names an ordered list
of endpoints. Images select `eye`, interrogations/reviews select `critic`, life
chapters select `chronicler`. An explicit `Writer(role=...)` overrides that
inference. Missing roles inherit the artist route, but a text-only endpoint is
never given an image. Outages advance immediately to the next configured
endpoint; the last endpoint has bounded retries. Validation failures also have a
bounded budget. JSON-schema constrained decoding is the default; `json_object`
and `prompt` are explicit compatibility modes, always with local Pydantic
validation. Cache identity includes endpoint/model, role, schema, generation
limit and image hashes. There is no silent downgrade from a schema to plain text.

OpenAI-compatible endpoints use `/chat/completions` relative to `base_url`
(include `/v1`); Anthropic uses `/messages` relative to its configured base URL.
Both support draft images. Model names, timeouts, token budgets and vision
capability are owner configuration. Credentials are environment references, not
literal keys. In Helm, `work.credentials[].secretKeyRef` injects them only into
the worker. The implementation never queries Kubernetes Secrets, follows HTTP
redirects, or retains provider error bodies. CLI backends remain explicit dev
options, with their prior capacity retry policy.

Privacy is enforced before both cache lookup and transmission. New Writer
instances classify input as `private`; only a trusted cluster endpoint can
receive it. Audited art callers explicitly opt into `data_class="art"`.
Self-portraits no longer receive infrastructure birth facts; composer and lineage
chapters receive projected art, not serialized events/state. Placeholder artist,
teacher and chronicler IDs do not leave the cluster. The inner critic receives
its artistic preferences, without internal history. Drawing error details remain
in the notebook and are not sent to a remote model. Composer images are made
before backup weaving, not from state-encoded scores.

This is an application boundary, not a classifier capable of discovering private
facts embedded in arbitrary prose. Callers must not label raw state as art, and
existing imported prose needs the same provenance guarantee. The old event-led
`write_story`, `khazar`, and `poetry` paths are deliberately private: an external
backend is refused rather than inventing an artistic replacement for their
literal event skeletons. Their redesign needs the person's artistic decision.

`music/notagen_batch.py` is opt-in via `MNEMOSYNE_NOTAGEN=self-hosted`.
`NOTAGEN_DIR`, `NOTAGEN_WEIGHTS`, and `NOTAGEN_DEVICE=cpu|cuda` select the installed
implementation, checkpoint and device. Workers load only for a batch, and worker
failures propagate instead of silently reporting success. Composer tells the
model whether NotaGen is available and refuses unavailable selections. The
optional painting path also requires an explicit `MNEMOSYNE_PAINT_MODEL`; it no
longer hardcodes a model repository. No model is required for rule-school
composition or lineage mechanics.

No free external music API with a verified service contract and suitable licence
was established in this investigation, so none was added. A public demo is not a
guaranteed API. [NotaGen's upstream](https://github.com/ElectricAlexis/NotaGen)
provides the self-hosted path;
[MusicGen's model card](https://huggingface.co/facebook/musicgen-large) specifies
CC-BY-NC 4.0 weights and does not establish such a free service.

### Optional chart and lifecycle

There was no existing Helm chart in this checkout. `charts/mnemosyne` adds a
small optional work-window runner; default values create only the configuration
ConfigMap. `work.enabled` creates a CronJob with no overlap, no automatic job
retry, a finite deadline, and an existing artifacts PVC. Its `servers` are
[native Kubernetes sidecars](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/):
startup probes gate the worker, and model containers terminate when the Job
finishes, including worker failure. Weights live on retained PVCs. Existing
endpoints need no sidecars. No model download, cluster-scoped permission,
PriorityClass or Secret is created automatically.

The chart requires an administrator-provided existing lowest-priority class
(negative priority, non-preempting); the tenant chart cannot prove it is lowest
without cluster-wide inspection. The default node allowlist is ws1/ws4. Supply
tested, pinned runtime/worker images and provision weights on the PVC first.
The command is explicit: the ordinary composer CLI uses workshop kubectl,
whereas a Job with no service-account token should use a local worker, such as
`hack/workshop/model_night.py` with a spec whose `servers` is empty (the chart
owns those servers). Results/spec/input should be under `/works`. This chart
was rendered and linted, not installed or runtime-validated in the cluster.

The generic sidecar contract can run llama.cpp, vLLM or Ollama with appropriate
commands, probes and GPU resource limits. Writer uses their compatible API;
these runtimes were not all integration-tested. For llama.cpp, configure a GGUF
text model and a separate supported vision model plus projection for the eye.
[The llama.cpp server contract](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
describes schema decoding and vision configuration.
[Qwen's GGUF card](https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF)
identifies the text MoE and Apache-2.0 licence; it is not a vision model.

### Evidence and remaining work

- `out/model-validation/tests.log`: 51 targeted tests, `OK`, 12.678 s.
  Writer retries, complete composer fixture, transport, drawing, climate,
  reception, lineage and model/chart tests were included.
- After adding role/cache and Anthropic image coverage,
  `out/model-validation/model-tests.log`: 10 tests, `OK`, 4.158 s.
- `helm lint charts/mnemosyne`: `1 chart(s) linted, 0 chart(s) failed`.
  `compileall` and `git diff --check`: no errors.
- NotaGen without opt-in exits with argparse's disabled-component error before
  loading weights. CPU/GPU inference with the new options was not run because
  both studios were already busy.
- `out/model-validation/external-mock-python.log`: a complete accepted fixture
  night, followed by chronicler/reception calls, made 13 real HTTP requests to a
  local mock server in 0.684 s. Process peak RSS was 94,568,448 bytes, including
  interpreter and fixtures. Musical output and answers were test doubles. The
  memory/time numbers are protocol-test costs, not external-provider performance
  or neural-model resource estimates. The privacy test injected canaries into
  birth facts, state, chapter facts, cluster identity, teacher IDs and taste
  history and verified they were absent from all outgoing requests.
- `/usr/bin/time -l` could not report memory in this sandbox:
  `sysctl kern.clockrate: Operation not permitted`. Python `getrusage` supplied
  the isolated process peak above instead.
- Initial privacy testing exposed cluster IDs in placeholder names/chronicler;
  this was corrected. A fixture-only reception registration omission was also
  fixed before the final passing tests.
- The broader `test_lineage_population.py` failed: `{'tower', 'hermit'}` missing,
  66.595 s, 291 lifespans, median 732 nights, range 91–945. It does not call
  Writer or the changed prose projections; no fate parameters were changed to
  make that unrelated population criterion pass.

**The requested real self-hosted composer night and quality comparison remain
unproved.** The preflight ran inside both allowed pods and returned exit 2:

| Pod | Current bytes | Limit bytes | Available bytes | Required bytes |
|---|---:|---:|---:|---:|
| studio-0/ws1 | 45,237,895,168 | 60,129,542,144 | 14,891,646,976 | 27,917,287,424 |
| studio-1/ws4 | 52,030,959,616 | 60,129,542,144 | 8,098,582,528 | 27,917,287,424 |

The 26 GiB check is a conservative launch budget for Q4 text weights, context,
vision/render headroom, not a measured model peak. Existing multi-process music
jobs were not stopped, and no model was loaded into insufficient headroom.
There was no installed llama-server in studio-0. No claims about prose or music
quality can be drawn from mock acceptance. A free work window, prepared llama
binary/text weights and a vision endpoint are still needed. Aesthetic comparison
must be made by the person using the retained drafts and model notes.

### Reproduction after a free studio window

Read-only preflight (already executed, no Secret access):

```sh
kubectl --kubeconfig ~/workshop.txt --context admin@workshop -n tenant-scheherazade \
  exec -i studio-0 -- /work/venv/bin/python - --preflight < hack/workshop/model_night.py
```

`hack/workshop/model_night.py` runs inside a pod, starts only explicitly listed
servers, rejects developer CLIs, applies a work deadline, and stops its own
server process groups on completion/failure/SIGTERM. It preserves notebooks,
render logs, server logs, input hashes, elapsed time, sampled cgroup memory and
largest-child RSS. Cgroup memory includes other jobs and is labelled accordingly.
`config/model-night.example.json` defines the spec; prepare its input files and
runtime paths in the pod, point the eye role to a vision server, then run:

```sh
kubectl --kubeconfig ~/workshop.txt --context admin@workshop -n tenant-scheherazade \
  exec studio-0 -- nice -n 19 env \
  PYTHONPATH=/work/model-check/src:/work/lineage-check/deps \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  /work/venv/bin/python /work/model-check/hack/workshop/model_night.py \
  --spec /work/model-check/night.json --out /work/model-check/selfhost-night-01
```

The example is not a claim those files/binaries have been installed. Copy the
current `src/mnemosyne`, `atlas`, harness and config into that isolated directory
first. Use a new output directory for every attempt. For a second genuine path
comparison, reuse the exact same lineage/inner files (check recorded hashes),
change only endpoint configuration, and keep caches separate. External mock
proof can be rerun locally without credentials or models:

```sh
PYTHONPATH=tests uv run python -m unittest \
  test_models.ModelTests.test_complete_external_mock_night_and_privacy_projection
helm lint charts/mnemosyne
```

Changes remain uncommitted. Existing rename/worktree changes were not staged.
Suggested logical commit messages after review and selective staging:

```sh
git commit --signoff -m "feat(models): configure role-based writers and enforce art-only egress" \
  -m "Assisted-by: LLM"
git commit --signoff -m "feat(workshop): add optional model windows and benchmark preflight" \
  -m "Assisted-by: LLM"
```

### Solitude and prolonged illness calibration (2026-11-04)

The population test file was retained byte for byte from the start of this
change. Its current horizon is 48 × **five** years, unlike the historical
20-year experiment above. In studio-0/ws1 it passed in 122.628 seconds:
285 completed lives, median 716 nights, range 15–1031. All twelve categories
occurred: rediscovered 241, school with heretics 1, craftsman 103, late bloomer
44, posthumous 15, rivals 26, late return 27, renunciation 3, hermit 32,
changed voice with subsequent work 14, meteor 7, prodigy burnout 1. The
existing lifespan, early-death, occupancy, season and event assertions passed.
Mortality and global encounter-rate parameters were not changed.

Thirteen lineage contracts, seven reception tests and seven climate tests
passed locally. New contracts cover relationship avoidance in both directions
and apprenticeship, prolonged illness across JSON restore, continued work
without a recovered event, vacancy limits and renunciation. The population
run used synthetic works only, no Writer or artist subprocesses.

Intermediate failures: the isolated pod copy first lacked the atlas; copying
it fixed startup. An initial solitude distribution (`sqrt(isolation)`) yielded
194 hermits and 15 changed voices but lost schools with heretics. The final
`isolation ** 4` distribution concentrates strong avoidance in the secluded
tail instead of suppressing relationships for most artists. Logs, the initial
source copy and the unchanged population-test copy are retained locally in
`out/lineage-retune/`; pod inputs are in `/work/lineage-retune-20261104`.

Reproduce the population check after copying current sources, tests and atlas:

```sh
kubectl --kubeconfig ~/workshop.txt --context admin@workshop -n tenant-scheherazade \
  exec studio-0 -- sh -c 'cd /work/lineage-retune-20261104 && nice -n 19 env PYTHONPATH=src:/work/lineage-check/deps /work/venv/bin/python -m unittest discover -s tests -p test_lineage_population.py -v'
```

Changes remain uncommitted. Suggested commit after review and selective staging:

```sh
git commit --signoff -m "fix(lineage): restore solitary lives and enduring changed voices" \
  -m "Assisted-by: LLM"
```

The additional 48 × 20-year check also passed every original assertion:
1,444 completed lives, median 721 nights, range 9–1031; hermit 72, changed
voice with subsequent work 73, schools with heretics 8, and all other required
categories present. The auxiliary `out/lineage-retune/twenty_years_parallel.py`
reads the original test, extends only the horizon and distributes independent
seeds across four low-priority processes; individual invariants and aggregate
assertions are reused from that test. The original test file remains unchanged.
Its full log is `out/lineage-retune/twenty-years-parallel.log`. An initial serial
20-year probe was stopped before restarting this auxiliary run in parallel;
its partial log is retained. Both experiments used only studio-0 on ws1.

To repeat the extended check after copying the auxiliary script:

```sh
kubectl --kubeconfig ~/workshop.txt --context admin@workshop -n tenant-scheherazade \
  exec studio-0 -- sh -c 'cd /work/lineage-retune-20261104 && nice -n 19 env PYTHONPATH=src:/work/lineage-check/deps /work/venv/bin/python twenty_years_parallel.py'
```

Final `compileall`, `git diff --check`, and byte comparison of the population
test against the start-of-task copy passed. No artistic decision remains for
this mechanical calibration; actual artistic output was not generated.
