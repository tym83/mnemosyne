# Climate (§71)

`sensor.Sensor.read(previous)` is a private, read-only sampler restricted to the
workshop namespace. It uses explicit standard resource names and optionally
metrics.k8s.io. It does not discover arbitrary resources, request Secrets,
exec into pods, or list namespaces/nodes/cluster roles. No raw Kubernetes
objects are persisted: inventory, image versions, counts and event identities
are retained privately for comparisons. Namespace deletion requires an explicit
NotFound, not a timeout or Forbidden. The first reading is a baseline, not a
birth/deployment/upgrade. Changing image sets is an observed workload upgrade;
control-plane upgrades cannot be inferred from tenant objects.

`mood([...readings])` dissolves samples into thirteen qualities. Unknown metrics
use a neutral prior; their absence remains recorded in the private observation.
Utilisation is usage / pod requests, not usage / node capacity. Service links
are endpoint membership, HA is a replica proxy, local role strictness is a
wildcard-rule proxy: effective RBAC, including ClusterRoleBindings, is unknown.
No latency API is assumed. Repeated weekday/hour samples establish the tenant's
own weekly baseline; a single reading cannot establish it. Memory has a 60-day
half-life. Existing scenario callers retain their interface and gain abundance
and novelty (their complements are scarcity and routine).

`climate.qualities` is the numeric allowlist at the fate boundary: finite bounded
numbers only. Facts, names, supplied prose, dates, versions and event identities
are discarded. Observer and artist sensitivities are deterministic per identity
and checkpointed. Fate, private taste, critic moods/fashion and audience tastes
use the resulting inner states. Birth climate is retained with every work;
rediscovery weights and conditional probability increase with climatic rhyme.
Legacy checkpoints lacking climate fields get neutral/default profiles.

Structural tendencies use beta samples weighted by climate and taste/method
identity. These are synthetic calibration coefficients, not artistic judgements.
The composer passes the sampled suggestions into sketch and draft planning,
retaining them in its notebook. A symphony also receives the abstract year shape:
3–5 equal expressive-mass intervals and a 32-point tension curve, without dates
or event-to-movement assignments. The artist still chooses idea and method and
interprets the suggestions. No new artistic doctrine or score is prescribed.

Occasions are a separate scheduler boundary: only genre, moment and publicity
are admitted by `Lineage.schedule`. Scenario and live adapters discard subjects
and event details. Future occasions wait until due; a work consumes one occasion.
Workshops may publish immediately. Circle/world editions are held until a fixed
monthly batch at least 30 days later. The public programme is constructed with
an allowlist, never by copying the private work: world uses a pseudonym and no
exact date or identifiers; circle omits dates; workshop retains internal IDs.
Private lineage/reception checkpoints are NOT public catalogues. Delayed batches
mitigate timing correlation, but a genre and a sparse output stream can still
reveal timing statistically; no anonymity guarantee is made.

Run mechanics without Writer:

```sh
uv run python -m mnemosyne.climate_run --cluster shop --out out/works/climate
uv run python -m mnemosyne.climate_run --live --out out/works/climate
uv run python -m unittest discover -s tests -p 'test_climate.py'
```

Run the annual numerical experiment in a studio pod, with the package, scenario,
atlas/theory/creation.yaml and dependencies available there. It creates synthetic
work measurements, not artistic works. The live command only reads APIs and
appends local private sensor history. Do not publish `sensor-private.json` or
`year.json`; the encrypted backup path remains separate and unchanged.
