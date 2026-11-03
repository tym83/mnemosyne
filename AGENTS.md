# Scheherazade — notes for coding agents

The cluster is an artist: it makes works in five arts (music, painting,
architecture, literature, perfumery), and the works are also its backup —
a work encodes the state of the cluster at a moment. This repository is
stage A: a synthetic year of four clusters (`scenarios/`), artists who find
an idea, a method and its shades, and works made from them, with every
sketch and draft kept as part of the work.

You are the implementer. Artistic decisions (what an idea is, what a sheet
should look like, whether a work is good) are made by the person who gives
you the task; when a task needs one, stop and say so in the report instead
of choosing.

## Layout

- `src/scheherazade/scenario/` — simulator of a cluster's year (signals, ops, facts).
- `src/scheherazade/mood.py` — the life of a cluster as qualities of experience.
- `src/scheherazade/artist.py` — self-portrait → idea → critic → method → halftones.
- `src/scheherazade/literature.py` — `Writer`: structured answers from `codex exec`,
  `claude -p` or the API, cached in `out/cache`.
- `src/scheherazade/drawing/` — paper architecture: `bpy_kit.py` (runs inside
  Blender), `run_sheet.py`, `sheets.py` (plan → draft → render → look).
- `src/scheherazade/music/` — NotaGen batches, analysis, selection.
- `atlas/` — methods, masters, theory of how masterpieces are made.
- `hack/workshop/` — the studio pods in the workshop cluster.
- `out/` — generated, not in git.

Run Python with `uv run python -m scheherazade.<module>`.

## Principles of the art (do not break them in code)

- No literalism: an event of the cluster never becomes an object in a work
  (no "month = hall", "incident = scar"). The life of the cluster reaches
  the artist only as feelings and shades.
- A work starts from an idea and a method; the process (idea, sketches,
  drafts, critique) is stored with the work.
- Speed does not matter. Priorities: backup > quality > background load.

## Workshop cluster

- Always `kubectl --kubeconfig ~/workshop.txt --context admin@workshop`.
- Only namespace `tenant-scheherazade` (pods `studio-0` on ws1, `studio-1` on ws4).
  Never touch other namespaces or tenants; never scale onto ws2/ws3.
- In the pods: Python with torch is `/work/venv/bin/python`; Blender is
  `/work/blender/blender`; NotaGen is in `/work/NotaGen/gradio`.
- Heavy work runs in the pods, not on the laptop.
- Never read or print Secrets.

## Git

- Your sandbox cannot write `.git` or start long runs that call Codex
  themselves (artists). Leave changes uncommitted and give the commit
  message and launch commands in the report; they are applied after review.
- Never commit to or push `main`. Do not push.
- Every commit: semantic message in English, `--signoff`, and exactly one
  trailer `Assisted-by: LLM`. No other attribution anywhere.
- Small commits, one per logical step. Never commit `out/` or secrets.
- Do not delete user data or generated works; if something must be
  removed, write the command in the report.

## Report

End with a short report: what changed (files), what you ran and what it
showed (real output, failures included), what is left, and any decision
that needs the person.
