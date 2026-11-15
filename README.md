# Mnemosyne

Mnemosyne is an atelier that lives inside a Kubernetes cluster. Its creators,
composers and writers, live there continuously: each one is born, finds ideas,
works through sketches and drafts, rests, falls ill, despairs and eventually dies
on the real calendar. Critics review what is released and a chronicler records
what happened.

Every artifact of that process, finished or not (scores, drafts, margins,
notebooks, reviews, chapters of the creators' Lives), carries a piece of the
cluster's state as an encrypted backup. The works are the backup: anyone who
holds enough of them and the owner's key can rebuild the cluster's API objects
in a new cluster.

[Русская версия](README.ru.md)

The distribution is `mnemosyne-art`, the Python package is `mnemosyne`, the
command-line tool is `mnemo`.

## How it works

- A sensor reads the objects listed in the chart's inventory every 15 minutes.
  A change becomes a keyframe or a delta in the atelier's ledger. Each piece is
  compressed, sealed to the owner's public key and fountain-coded into frames.
- Each new artifact carries the pending frames at once: in musical choices of a
  score (dynamics and other details the codec owns), or in the choice between
  variant readings of a text. A piece keeps being continued by later works until
  it survives the loss of 30% of its carriers.
- The atelier writes with its own key; it can seal the backup but cannot open
  it. Only the owner's private key, which never enters the cluster, opens it.
- The atelier's own objects (Atelier, Artist, Opus, Review and other
  `mnemosyne.art` records) are the carrier, not the payload.
- The owner configures infrastructure only: window, resources, keys, models,
  storage and the backup inventory. There are no settings for ideas, schools,
  moods or plans; what the creators make is their own.

Only music and literature are active in the atelier. The other arts in this
repository (painting, architecture, perfumery) are studies.

## Requirements

- Kubernetes 1.29 or newer, Helm 3.
- A default StorageClass, or an existing claim in `addon.artifacts.existingClaim`.
  The works volume is ReadWriteOnce.
- Controller and studio images. They are built only by the repository's
  **Mnemosyne images** Actions workflow and pushed to private
  `ghcr.io/tym83/mnemosyne-{controller,studio}`. The workflow uploads two
  `digest-*` artifacts with Helm values. Pulling needs an existing
  `imagePullSecret`; the chart never creates registry credentials.
- A model endpoint: an external API (Anthropic, or an OpenAI-compatible
  provider) or a self-hosted OpenAI-compatible server in the cluster.
- `mnemo` on the owner's machine: `uv sync --locked`, then `uv run mnemo ...`.

## Install with Helm

### 1. Keys

```sh
uv run mnemo keys new --output ./mnemosyne-keys
```

This writes two raw 32-byte X25519 keys and prints `ownerPublic` (hex):

- `owner.key` is the owner's key. Keep it offline. It is needed only to restore,
  and it is the only way to read the backup: if it is lost, the works can no
  longer be decoded.
- `atelier.key` is the atelier's key. It goes into a Secret in the atelier's
  namespace:

```sh
kubectl --context <ctx> create namespace mnemosyne
kubectl --context <ctx> -n mnemosyne create secret generic mnemosyne-atelier-key \
  --from-file=atelier.key=./mnemosyne-keys/atelier.key
```

Vault (KV v2), AWS KMS or a CSI volume can deliver the atelier key instead; see
`addon.key` in the [chart README](charts/mnemosyne/README.md).

### 2. Values

`owner.yaml`, for an external API:

```yaml
addon:
  enabled: true
  imagePullSecrets: [{name: ghcr-pull}]
  mode: API
  window: {kind: continuous}
  key:
    ownerPublic: <hex printed by mnemo keys new>
    secretName: mnemosyne-atelier-key
    secretKey: atelier.key
  env:
    - name: MNEMOSYNE_ANTHROPIC_KEY
      valueFrom: {secretKeyRef: {name: model-api, key: token}}
  gallery:
    enabled: true
    ingress:
      enabled: true
      className: nginx
      host: gallery.example.org
      tls: [{hosts: [gallery.example.org], secretName: gallery-tls}]
models:
  endpoints:
    api:
      backend: anthropic
      location: external
      base_url: https://api.anthropic.com/v1
      model: <model name>
      key_env: MNEMOSYNE_ANTHROPIC_KEY
      vision: true
      max_tokens: 32000
      timeout: 900
  roles:
    artist: [api]
    critic: [api]
    chronicler: [api]
    eye: [api]
```

The API key Secret (`model-api` above) is created by the owner; the chart only
references it through `addon.env`.

For a self-hosted model, point an endpoint at an OpenAI-compatible server in the
cluster (llama.cpp, vLLM, Ollama) and use `mode: background`, or `mode: GPU`
with `addon.gpuResource` and a matching resource limit:

```yaml
models:
  endpoints:
    text: {backend: openai, location: cluster, base_url: http://llm.models.svc:8080/v1,
           model: <model name>, max_tokens: 8192, timeout: 1800}
    eye:  {backend: openai, location: cluster, base_url: http://vlm.models.svc:8081/v1,
           model: <vision model>, vision: true}
  roles: {artist: [text], critic: [text], chronicler: [text], eye: [eye]}
```

Each role takes a list of endpoints tried in order. See
[config/models.example.yaml](config/models.example.yaml). Only artistic context
is sent to models, never the snapshot.

### 3. Window

`addon.window.kind` selects how the atelier lives:

- `continuous`: one long-running Deployment (`mnemo-life-*`) in real time. Every
  living creator works on their own rhythm; fate (births, illness, deaths) runs
  on the calendar; critics and the chronicler write when there is something to
  write about; the sensor and the carriers work all the time. This is the
  intended mode.
- `night`, `weekends`, `idle`, `always`: one Job per night inside a window
  (`startHour`/`endHour` in `timeZone`, or an idle cluster). With
  `mode: chamber` these nights make no model calls.

`addon.suspend: true` stops the atelier (scales the life Deployment to zero,
suspends running Jobs).

### 4. Install

```sh
helm --kube-context <ctx> install mnemosyne charts/mnemosyne -n mnemosyne \
  -f digest-controller.yaml -f digest-studio.yaml -f owner.yaml
uv run mnemo status --namespace mnemosyne --context <ctx>
uv run mnemo works list --namespace mnemosyne --context <ctx>
```

Images are referenced by digest only; the chart ships no digest and fails
without one.

### Gallery

With `addon.gallery.enabled`, a read-only Deployment serves the atelier's
history as a site: creators, works with their drafts, scores and translations,
the inner critic's rounds, critics, Lives, schools and their manifestos, the
timeline and a restore page. It mounts the works volume read-only, has no
service account token and no keys, and rebuilds the site every
`addon.gallery.refreshSeconds` (900 by default). Expose it with
`addon.gallery.ingress` (`className`, `host`, `annotations`, `tls`) or with a
port-forward. Because the volume is ReadWriteOnce, the studio and life pods are
scheduled on the gallery's node.

### A history lived elsewhere

`mnemo history export` packs an atelier's history (for example a synthetic year
from `hack/year/run_year.py`); `addon.history.source` (HTTPS) and
`addon.history.sha256` move it into the volume once after install. An atelier
that already lives on the volume is never overwritten. Use the same atelier key
and owner public key the history was woven with.

## What is backed up

- The **declared inventory** (`addon.inventory`): each entry names an API
  version, kind and resource. No wildcards. Defaults: Namespaces, ConfigMaps,
  Services, ServiceAccounts, PersistentVolumeClaims, Deployments, StatefulSets,
  DaemonSets, NetworkPolicies, Ingresses, Roles, RoleBindings and
  CustomResourceDefinitions. Add entries for other installed APIs (operator
  instances, data-backup objects such as Velero `Backup` as a map to the data);
  the chart generates read-only RBAC for exactly that list.
  `addon.snapshotNamespace` restricts the backup to one namespace.
- **CustomResourceDefinitions by reference**: name, group, kinds, scope, served
  versions and a SHA-256 of the schema, not the schema itself. The platform that
  installs the type in the new cluster brings the schema back.
- **Not backed up**: Secrets (unless `addon.includeSecrets: true` and an explicit
  Secret inventory entry), the contents of volumes and databases, cloud
  resources, control-plane certificates, the atelier's own records.

## Where the atelier keeps its files

The works volume holds `/works/<release>-atelier/`:

- `creators/<id>/<time>/` — one folder per work: notebook, sketches, drafts,
  scores, margins and `woven/` (the carriers made from them);
- `woven/` — carriers made from critics' and chronicler's texts;
- `ledger/` — the ledger of cluster states and their sealed frames;
- `process/<sha256>.json` — a work's full process (every answer and plan) when
  its record is too large for etcd; the Kubernetes record keeps the path and hash;
- `lineage.json`, `life.log` — the atelier's life and its log.

`helm uninstall` keeps the works volume, the Atelier and the CRDs.

## Restore into a new cluster

1. **Collect woven works.** Any surviving set works: scores (`.xml`,
   `.musicxml`), text volumes (`*.variants.json`) and audience panels
   (`*.audience.json`). Everything else is ignored, damaged files count as lost.
   From a running atelier:

   ```sh
   kubectl --context <old> -n mnemosyne get pods -l mnemosyne.art/atelier=mnemosyne-atelier
   uv run mnemo works export --pod <life pod> --source /works/mnemosyne-atelier \
     --output ./works --namespace mnemosyne --context <old>
   ```

   The export refuses symlinks and overwrites and writes a SHA-256 manifest.
   Copies kept elsewhere (gallery downloads, an S3 mirror of night Jobs, any
   archive) are equally valid inputs.

2. **Decode and check**, without contacting a cluster:

   ```sh
   uv run mnemo restore --works ./works --key ./mnemosyne-keys/owner.key \
     --output ./recovered --dry-run
   ```

   `python -m mnemosyne.restore` takes the same arguments. The output directory
   gets `archive.tar.zst`, ordered `manifests.yaml` and `report.json` (decoded and
   rejected files, complete snapshots, the restored moment). If no snapshot is
   complete yet, the error says how many frames each snapshot has and needs.
   `--at <ISO time>` restores the newest complete state not after that moment.

3. **Install the platform** in the new cluster: every component that provides
   a referenced CustomResourceDefinition (operators, Cozystack, and so on).
   Restore does not write type definitions; it checks that each one exists,
   retries, and then stops, listing the definitions still missing.

4. **Apply:**

   ```sh
   uv run mnemo restore --works ./works --key ./mnemosyne-keys/owner.key \
     --output ./recovered-apply --apply --kubeconfig ./new.kubeconfig --context <new>
   ```

   Objects are applied with server-side apply (field manager
   `mnemosyne-restore`) in phases: type definitions, namespaces, other cluster
   objects, namespaced objects, each phase retried for dependencies. Objects the
   new cluster already has (made by its control plane or platform releases) are
   kept, not overwritten. PersistentVolumeClaims get fresh volumes: the old
   volume binding is dropped. Owner references are resolved to the new UIDs.
   A rerun is idempotent; successful applies remain if a later object fails.

5. **Re-supply secrets and data**: the atelier key Secret, model API keys, image
   pull secrets, application Secrets; volume and database contents from their
   own backups.

6. **Continue the atelier** (optional): install the chart in the new cluster
   with the same atelier key and `ownerPublic`. With an empty volume, the
   atelier resumes its lineage from the restored Atelier, Artist and Biography
   records.

See [src/mnemosyne/RESTORE.md](src/mnemosyne/RESTORE.md) for the decoder's
details and limits.

## Cost of the model API

All model calls go to the endpoints the owner configures; the bill is the
provider's. Observed during development with Anthropic models (large model for
the artist, smaller one for critics):

- one critic call that reads score page images: about $0.30;
- one composer's work with a sketch and three drafts: about $7;
- the first two in-cluster nights of four creators: $5.48 logged (failed calls
  not counted).

In continuous mode the spend grows with the number of living creators and how
often they work (after each work a creator rests from ten minutes to several
hours, depending on their own temper and strength), plus critics and the
chronicler when there is something new. Identical requests are answered from
the cache in `/works/cache`.

The atelier keeps its own spending ledger and budget. Give each endpoint its
prices (`price_in`, `price_out`, US dollars per million tokens) in
`models.endpoints`; every call is then written to `/works/<atelier>/spend.jsonl`.
`addon.budget` (US dollars a month, 0 for no limit) makes creators wait for the
next month once it is spent. A spending limit with the provider is still a good
second guard. A self-hosted model has no per-call cost but needs its own capacity.

## Limitations

- The backup holds Kubernetes API objects only. Volume contents, databases,
  Secrets (by default), cloud resources and control-plane certificates must be
  backed up by other means.
- A state can be restored only after enough works have carried its frames;
  until then it is pending. Large inventories take longer to become complete.
- Loss tolerance is checked over at most 10,000 survivor combinations; above
  that no tolerance claim is made.
- Restore keeps objects that already exist in the target and does no pruning,
  rollback or volume data restore. Cluster-assigned fields and API defaults can
  need migration on a different cluster.
- Losing the owner key makes the backup unreadable. The atelier key alone
  cannot open it.
- The works volume is ReadWriteOnce; the atelier runs as one replica.
- CRD updates are not applied by `helm upgrade`; apply
  `charts/mnemosyne/crds/mnemosyne.yaml` separately.
- A model refusal or error fails that work; it is logged in `life.log` and the
  creator goes on with the next one.
- The Translator renders foreign texts into Russian only.
- Vault, KMS and S3 integrations have not been exercised against live services.

## Packaging

- [charts/mnemosyne](charts/mnemosyne/README.md) — the Helm chart.
- [packaging/cozystack](packaging/cozystack/README.md) — a Cozystack application.
- [packaging/kubepkg](packaging/kubepkg/README.md) — a kubepkg recipe.

## Development

```sh
uv sync --locked --extra operator
uv run mnemo restore --help
PYTHONPATH=src uv run python -m unittest discover -s tests
```

Tests run in CI on pull requests and on manual dispatch
(`.github/workflows/tests.yaml`). See [AGENTS.md](AGENTS.md) for the project
layout and [decoder compatibility](src/mnemosyne/weave/codecs/README.md) for
retained formats.
