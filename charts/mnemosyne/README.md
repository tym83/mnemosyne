# Portable atelier add-on

The `addon` section adds a namespaced kopf controller and one studio Job per
Atelier/night. Existing `work` and `models` values retain their earlier behavior.
The add-on is disabled until real image digests, the atelier key reference and
the owner's public key
are supplied. No fabricated digest is shipped.

The owner configures infrastructure only: window, resources, key, models,
storage and snapshot scope. There is no setting for ideas, schools, plans,
moods or climate. The climate is read by a read-only sensor in the atelier's
namespace (forbidden reads stay unknown) and reaches artists only as felt
qualities; everything else is the atelier's own creative freedom.

## Installation

1. After reviewing changes, run the repository's **Mnemosyne images** Actions
   workflow. It builds/pushes only in Actions, to private
   `ghcr.io/tym83/mnemosyne-{controller,studio}`. Existing non-private packages
   cause the workflow to fail. Download the two `digest-*` artifacts. Configure
   an existing `imagePullSecret` for private GHCR pulls; the chart never creates
   or reads registry credentials.
2. Prepare `owner.yaml` with `addon.enabled: true`, `addon.key.secretName` (an
   existing Secret holding 32 **raw** X25519 private bytes), `imagePullSecrets`,
   and commissions: each has `idea`, `method`, and a complete approved school
   `plan`. Existing `music/schools/plans` are technical method studies, not
   evidence of artistic quality. `mnemo keys new --output DIR` creates the owner's
   key (keep it offline: only it opens snapshots) and the atelier's key (mount it
   as the Secret); set `addon.key.ownerPublic` to the printed hex. The atelier
   seals snapshots it cannot open and authenticates frames with a secret both
   keys derive; its public key travels in every work.
3. Install into a dedicated namespace:

   ```sh
   helm install mnemosyne charts/mnemosyne --namespace mnemosyne --create-namespace \
     -f controller.yaml -f studio.yaml -f owner.yaml
   mnemo status --namespace mnemosyne
   mnemo works list --namespace mnemosyne
   ```

A default StorageClass or `addon.artifacts.existingClaim` is required. Kubernetes
conformance does not itself provide storage provisioning. The chart has no
workshop node names, privileged pods, ingress controller or vendor API dependency.
Generated Jobs use the minimum int32 PriorityClass and Never preemption; an
existing priority class can be explicitly selected instead. The scoped quota
applies to that class, not unrelated workloads in the namespace.

`addon.window.kind` supports `night`, `weekends`, `idle`, `always`. Night hours
are interpreted in `timeZone`, including overnight and DST transitions. A Job
cannot exceed the remaining clock window or `deadlineSeconds`. Idle requires
no pending pods, no node pressure and CPU below 20% of allocatable on every node.
Without metrics.k8s.io it fails closed. This is an admission heuristic, not a
promise that foreground resource use cannot change between observations.
Suspension stops pods; the next admission creates a retained new attempt within
the same Job. Completed/failed Jobs are kept so controller restart cannot repeat
a night. There is no automatic retry of a failed night. Use a new night/Atelier
for an explicitly requested retry; do not delete notebooks.

## Modes and keys

- `chamber`: no model calls. Every work the artists' lives bring that night,
  accepted or not, gets a score from a school the artist chooses (their own
  school, or traditions they have not tried yet); then weave, optional audio
  and decode.
- `background`: existing composer with configured cluster model endpoints.
- `GPU`: the same pipeline plus an explicitly supplied `gpuResource` and matching
  resource limit. Models/endpoints and device plugin are supplied by the owner.
- `API`: explicit external endpoint opt-in; credentials enter through `addon.env`
  valueFrom references. Only artistic context goes to models, never the snapshot.

`models` config routes artist, critic, chronicler and eye through the existing
model policy. The optional old `servers` runner remains separate; the add-on
uses reachable cluster model endpoints. NotaGen is an optional image target,
with a separately reviewed upstream revision and mounted licensed weights;
its pinned legacy dependencies live in their own Python environment.

`addon.key.provider`:

- `file` (default): read `key.path` from the read-only `/key` mount. Use
  `secretName/secretKey`, or `key.volume` for a pre-existing PVC/projected/CSI
  volume. No Secret GET permission is needed for mounting the key.
- `vault`: `vault.address` must be HTTPS, `path` is a KV v2 API path such as
  `secret/data/mnemosyne`, `field` contains base64 of the raw key, `tokenFile`
  points to a separately mounted token. Optional Vault namespace is supported.
- `kms`: AWS KMS Decrypt of `kms.ciphertextFile`, explicit `keyId`, optional
  `region` and `encryptionContext`. Uses the AWS credential chain. Other KMS
  providers can deliver a file through the owner-supplied CSI volume.

The chart does not install Vault, KMS, CSI drivers, model servers or GPU plugins.
Live Vault/KMS/S3 integrations have not been exercised in this workspace.

## Backup boundary and records

The studio reads the **explicit inventory** of GVK/resource names. The defaults
cover common desired-state resources and every Mnemosyne record. Extend inventory
and hence generated read-only RBAC for additional installed APIs. No resource
wildcards are accepted. Collection failures fail the night instead of silently
omitting a declared resource. Optional `snapshotNamespace` restricts the collector;
its reader ClusterRole is still cluster-scoped by default. For tenant-only
authorization, set `addon.rbacScope: namespace`, `snapshotNamespace` to the
release namespace, an explicit namespaced inventory and an existing
`priorityClassName`. This emits Role/RoleBinding instead, omits cluster discovery
grants (normal authenticated Kubernetes discovery must be available), and rejects
cluster-wide idle detection. Install CRDs separately and use `--skip-crds` for
tenant installations. `addon.manageQuota: false` delegates quota management to
platform tenant quotas; defaults preserve the original standalone behavior.

Secrets require **both** `includeSecrets: true` and an explicit Secret inventory
entry. Restoring such an archive additionally requires `mnemo restore
--include-secrets`. No live Secrets were read during development/testing.
The key itself is never stored with the works. Backup covers Kubernetes objects,
not PVC volume bytes, databases, cloud resources or control-plane certificates.
API defaults and cluster-assigned addresses can need migration on another
cluster. This is not yet a demonstrated full-cluster disaster recovery system.

State is captured before the night; it does not enter the artistic pipeline.
Fate and commissions run from retained lineage; their resulting records are
published for the next snapshot. The checkpoint lives on the works PVC; if it is absent, Artist/Biography/Atelier
CRs restored into the new cluster provide the lineage checkpoint.
The namespace's Atelier retains runtime configuration when lineage is patched.

The existing versioned dynamics/fountain codec carries ciphertext in musical
choices; metadata carries the authenticated catalogue, not the payload. Every
carrier is decoded before publishing. The full recovered archive must match
byte for byte. Insufficient scores produce `PendingCapacity`. Full recovery and
30% work loss are reported separately. At most 10,000 survivor combinations are
checked exhaustively; above that limit no loss-tolerance claim is made. Small
generations may reseal up to eight times to improve transport rank, without
changing the approved musical material.

All ten emitted kinds have structural schemas, status subresources and printer
columns. Runtime fields are typed; narrative record fields deliberately retain
unknown content for compatibility. CRD updates are not applied by Helm upgrades:
review `charts/mnemosyne/crds/mnemosyne.yaml` and apply it separately when upgrading.
Regenerate schema files with `uv run python hack/addon/schema.py`.

## Export, restore and retention

```sh
# Mounted PVC, or --pod <existing-studio-pod> with explicit context for a remote PVC:
mnemo works export --source /works --output /safe/works
# S3 uses normal AWS credentials; --endpoint supports compatible object stores:
mnemo works export --source s3://my-bucket/mnemosyne --output /safe/works
# Select ONE snapshot/night; mixing multiple complete snapshots is rejected:
mnemo restore --works /safe/works/<atelier>/<night>/woven --key /safe/owner.key \
  --output /safe/recovered --apply --kubeconfig /safe/new-kubeconfig --context new
```

An export refuses overwrites and symlinks and writes a SHA-256 file manifest.
S3 mirrors the PVC after verification and publication; its completion marker is
uploaded last. The PVC is retained even when S3 is configured, to preserve failed
attempts and lineage. S3 objects are never deleted by uninstall. `helm uninstall`
keeps the works PVC, Atelier and CRDs (and therefore other artistic CRs). Deleting
the namespace or CRDs is a separate destructive operation. Explicitly set
`addon.artifacts.keep: false` before uninstall only if removal is desired;
externally supplied claims are never owned by this chart.

## A lived history and the gallery

An atelier can arrive with a history lived elsewhere, for example a year run
by `hack/year/run_year.py`. Pack it, publish the archive where the cluster can
fetch it over HTTPS, and give its digest:

```bash
mnemo history export --root out/year/leonia-year --out leonia-history.tar.gz
# prints the sha256
helm upgrade --install atelier charts/mnemosyne -n atelier \
  --set addon.enabled=true \
  --set addon.history.source=https://example.org/leonia-history.tar.gz \
  --set addon.history.sha256=<sha256> \
  --set addon.gallery.enabled=true
```

After install a Job unpacks the archive into the atelier's directory on the
volume: lineage, nights, works, notebooks, carriers and the ledger. It refuses
an archive that contains keys and never overwrites an atelier that already
lives there. The studio's next night continues that life. Install with the
same atelier key and owner public key the history was woven with, so the
ledger goes on in one chain; restore the cluster state the history describes
with `mnemo restore --works <dir> --key owner.key --apply` before or after.

The gallery serves the history as a read-only site: creators, works with their
drafts, scores and translations, the inner critic's rounds, critics, Lives,
schools with their manifestos, the timeline and how to restore. It mounts the
volume read-only, has no service account token and no keys, and rebuilds the
site every `addon.gallery.refreshSeconds`. Expose it with
`addon.gallery.ingress` or a port-forward to share it. The volume is
ReadWriteOnce, so with the gallery on, the studio is scheduled on its node.

## Validation and release gates

```sh
uv sync --extra operator
uv run --extra operator python -m unittest discover -s tests -p test_addon.py
helm lint charts/mnemosyne
# Equipped Linux studio/CI, Podman or nerdctl only. No local/pod image builds:
uv run --extra operator python hack/addon/kind_e2e.py --provider podman \
  --base-image 'python@sha256:<reviewed-python-3.12-digest>' --output /safe/new-e2e-run
```

Source e2e uses Helm's post-renderer only for the disposable kind cluster:
controller and studio run repository source in Python bootstrap pods, with
host-mounted source and exported artifacts. `render: false` avoids requiring
audio tools in that bootstrap image (in production it keeps accepted works as
scores, drafts and notebooks only: the backup never depends on sound); the real studio smoke separately exercises
rendering. It creates three technical study carriers from live Namespace and
ConfigMap state, verifies all two-of-three survivor sets, exports, deletes only
its own random-named kind cluster, creates a fresh one, applies restore and
compares both live normalized objects. It never auto-deletes failed evidence
or the final cluster. A workflow_dispatch CI entry point is provided.

This fixture does not establish П.2 for arbitrary cluster size or APIs. Release
requires actual Actions image builds, successful kind/Helm round-trip, larger
inventories and capacity evidence, and owner review of artistic results.
Reference contracts: [kopf timers](https://docs.kopf.dev/en/stable/timers/),
[kind Podman/nerdctl](https://kind.sigs.k8s.io/docs/user/rootless/),
[Buildx attestations](https://docs.docker.com/build/ci/github-actions/attestations/).

## Workspace validation, 2026-11-04

- `helm lint charts/mnemosyne`: `1 chart(s) linted, 0 chart(s) failed`.
- Targeted unittest suites: addon **14**, composer/transport **10**, model chart
  **2**, state collector **6**, restore **7**, rename **4** — **43 tests passed**.
  Python compile checks and `git diff --check` passed; both workflow files parsed
  as YAML. No Actions/image build or live controller deployment was run.
- Source smoke in **studio-0/ws1**, namespace **tenant-scheherazade**:
  `/work/addon-check-20261104/run-6`. Three existing tempo-canon technical studies,
  each 180 seconds, produced scores, PDFs and 182-second audio including tails.
  Exported MusicXML restored the real namespace + public root-CA ConfigMap
  snapshot: **2 objects, 935 bytes**, SHA-256
  `46893cfd5295bc65f5d7154568af01cbefa82683979b59e0340af8a89607d6c8`.
  `frame_decode_verified`, `archive_recovered`, `post_render_decode_verified`
  and `loss_tolerance_verified` were all **true**. All **3** two-of-three survivor
  sets had full rank; an actual two-score export also recovered identical bytes.
- Earlier attempts were retained: missing `atlas/theory/creation.yaml` exposed
  the source asset dependency; a 1-frame/2-source-frame result correctly reported
  `PendingCapacity`, then frame sizing was corrected. One intermediate loss
  assertion used stale copied worker source; transfer was corrected and the
  final full render passed. No failed notebooks or generated works were deleted.
- Renderer warnings remain: conflicting/discarded absolute dynamics, compressed
  LilyPond pages, FluidSynth `No preset found on channel 9 [bank=128 prog=0]`.
  This is a technical recovery result, not an artistic approval of the scores.
- kind preflight on the laptop stopped with
  `missing podman; Docker fallback is forbidden`. The studio has neither kind
  nor Podman/nerdctl; `unshare -Ur true` returned `Operation not permitted`, and
  cgroups are read-only. Full install → delete kind → new kind → apply/compare
  is therefore **prepared but not run**. CI must establish this release gate.
- Other unverified paths: private GHCR image builds/architectures, live kopf/RBAC,
  S3, Vault/KMS, GPU/API nights. Large snapshots can remain `PendingCapacity`;
  this version does not automatically aggregate a pending snapshot across later
  nights. Enough approved carrier material must be available in one night.

Suggested separate commits after reviewing/staging the relevant files (do not
include the pre-existing rename or unrelated changes accidentally):

```sh
git commit --signoff --trailer 'Assisted-by: LLM' -m 'feat(operator): orchestrate portable atelier nights and works export'
git commit --signoff --trailer 'Assisted-by: LLM' -m 'feat(packaging): add retained Helm deployment and private image builds'
git commit --signoff --trailer 'Assisted-by: LLM' -m 'test(e2e): add source-based kind recovery and studio verification'
```

No commits, pushes, workflow dispatches, Docker invocations or Secret reads were
performed in this task. The owner still supplies artistic commissions and reviews
the generated works; the technical fixture does not decide their artistic value.
