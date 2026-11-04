# Lineage and Lives

`lineage.Lineage` owns a nightly state machine and a private seeded RNG. It
receives only `mood(...)["qualities"]`, never incident identities. Birth of the
first artist is the scenario start. Other births fill creative vacancies.
`Parameters.spaces` limits working/ill artists to 1–3; silent people remain
alive, age, encounter others, and receive chapters. Ready returners precede
newcomers when a place opens. Death never frees or destroys archived works.

Health, creative energy, skill, maturation, openness, drive, resilience,
attachment, grief, faith, isolation, recognition, money, commercial pressure
and fertility interact. No artist is assigned a trajectory label. Relationships
are directed, weighted records; their endpoints may include dead teachers.
External-atelier relations can use the same edge schema, but no cross-cluster
broker is implemented. Poverty and commercial pressure are optional through
`Parameters.money_enabled`.

Rates and lifecycle thresholds live in `Parameters`, in nights. Defaults put
maturity at 180 nights, late age at 1400 and rising old-age mortality after
2200. A rare accidental death has probability 0.000025 per night. Illness
requires sustained heavy inner life plus rejections and low vitality; its
14/30/45-night course has recovery and death branches. These are synthetic
calibration choices, not medical or historical claims. Silent people are not
removed to enforce a living-population cap.

The work stub samples a four-dimensional feature vector and compares it with
**the entire own catalogue**. Quality, novelty and Shahryar's acceptance are
synthetic measurements. Rejected work remains in the Salon des Refusés and can
be rediscovered after at least 730 nights. A dying artist completes a last-work
stub before its status becomes dead. No later work can be added. The notebook
records preparation, incubation, dreams, illumination and verification; an
illumination can still be refused. Fertile and fallow periods require sustained
state, rather than a calendar date.

Artistic integration boundaries:

- `Artist.problem` accepts a problem previously set by the artist;
  `Lineage.idea_seed(id)` supplies the current insight to
  `artist.statement(..., illumination=seed)`. Shahryar still interrogates it.
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

`state()` / `restore()` preserve RNG and all history through JSON.
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
uv run python -m scheherazade.lineage shop bank --seed 17
```

Outputs: `out/works/lineage/{shop,bank}.{md,json}` plus atelier manifests and
content-addressed book files under `out/works/lineage/atelier/`. `--words` is
optional and calls the configured Writer backend; launch only after review in
accordance with AGENTS.md. Existing artwork is never deleted.

Contract tests: `uv run python -m unittest discover -s tests -p test_lineage.py -v`.
Population test: `python -m unittest discover -s tests -p test_lineage_population.py -v`
in the studio environment with the package on PYTHONPATH. It runs 48 independent
20-year histories and classifies the *observed* lives using work quality,
chronology, periods, relationships, silence and recognition. These labels are
never seen by the engine. The test also bounds lifespan statistics, checks that
the dead do not produce works and that creative occupancy never exceeds capacity.

## Validation of this implementation

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
