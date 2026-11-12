# Cozystack tenant application

This is an external package tree, maintained here; nothing is copied back into Cozystack. `apps/mnemosyne` uses the same nested HelmRelease pattern as Qdrant and Bucket. `system/mnemosyne-core` is staged from the unchanged portable chart layout; `system/mnemosyne-rd` registers the ApplicationDefinition and installs shared CRDs and the lowest, non-preempting PriorityClass once. The main chart remains installable with plain Helm.

## Build and registration

From the repository root:

```sh
uv run python hack/addon/schema.py
uv run python packaging/generate.py
uv run python packaging/prepare.py --output out/packages-new
helm lint out/packages-new/cozystack/apps/mnemosyne -n tenant-example
helm template mnemosyne-example out/packages-new/cozystack/apps/mnemosyne -n tenant-example
helm lint out/packages-new/cozystack/system/mnemosyne-rd
helm template mnemosyne-rd out/packages-new/cozystack/system/mnemosyne-rd --include-crds
```

`prepare.py` only reads the other checkout. It copies the expected `cozy-lib` (chart version `0.0.0` in the reference checkout) into the staging tree for both the package library mechanism and standalone Helm checks. `packaging/platforms.lock.yaml` records reference revisions; `sources.sha256.json` records the actual staged contents. Use `--cozystack PATH` for a different read-only checkout. Revalidate before changing the library version.

For a distributable build, add `--release --values controller.yaml --values studio.yaml --values owner.yaml` to preparation as documented in `../kubepkg/README.md`. The Cozystack catalog receives the two image pins but keeps instances disabled until the tenant supplies its own key. Tenant-specific owner values are not embedded in the Cozystack core chart.

A platform administrator publishes **the contents of** the staged `cozystack/` directory as a Flux OCI package tree, creates `OCIRepository/mnemosyne-packages` in `cozy-system` pinned to that artifact digest, then applies `packagesource.yaml`. Its Package activates the default variant, depending on `cozystack.cozystack-engine`. No built-in bundle is modified; this is equivalent to an external opt-in PaaS catalog package. The generated ExternalArtifact names are `mnemosyne-application-default-{mnemosyne,mnemosyne-core,mnemosyne-rd}`. The source must be available before applying the Package. Do not apply any of these platform-scoped objects to workshop.

Only the registration component is installed globally. Every `apps.cozystack.io/v1alpha1` `Mnemosyne` object is namespaced, creates an app release prefixed `mnemosyne-`, then a core release suffixed `-system`. Tenants never install CRDs or PriorityClasses. On upgrades, the platform administrator reviews and applies the staged CRDs separately: Helm does not upgrade its `crds/` directory. Uninstalling the catalog must not delete CRDs or retained works.

## Tenant values and access

The ApplicationDefinition carries the exact generated `values.schema.json`, including preset choices and the storage-class dashboard selector. `WorkloadMonitor` reports the controller, including zero replicas while disabled. No new Grafana dashboard is shipped: Mnemosyne has no Prometheus metric contract yet. The platform's existing workload dashboards remain applicable.

`mode: chamber`, `enabled: false`, `suspend: true`, a 01:00–06:00 UTC window and `s1.small` are defaults. Chamber composes without models: every work the artists' lives bring gets a score from a school the artist chooses. No setting supplies ideas, schools, moods or climate; the climate comes from the read-only sensor. Background uses explicitly configured model endpoints under `models`; it does not install models, assume GPU access or call an external API by default. Set `enabled: true` only after supplying image pins, and the existing recipient key Secret name; set `suspend: false` to admit work. `s1.small` gives a studio limit of 1 CPU/2 GiB and requests derived by cozy-lib's allocation ratios. Larger methods can select a larger preset. The controller has separate small core-chart limits.

The wrapper fixes `rbacScope: namespace`, the snapshot namespace to the release namespace, `includeSecrets: false`, a namespaced inventory and an administrator-owned PriorityClass. Tenant input cannot replace that inventory or enable cluster idle detection. API discovery uses Kubernetes' normal authenticated discovery permissions. Only Role/RoleBinding are emitted by an active tenant core release. Existing tenant ResourceQuotas govern admission; the wrapper disables the core's per-priority quota because a shared PriorityClass would otherwise make several ateliers count against each other's quota. Resource requests and limits still apply to each studio.

The platform's `view` tier reads applications; the registration chart adds a narrow aggregate-to-tenant-admin grant for `mnemosynes`, so `admin` manages them, and `super-admin` retains the platform's broader rights; this wrapper adds only read access to its WorkloadMonitor and named Atelier for `view` and higher, using cozy-lib's parent-tenant inheritance. `use` receives no extra write permission. No Secret or encryption key is exposed as a dashboard resource. Each tenant has independent PVCs, keys, runtime and retained records.

## Tenant storage and optional S3

`size: 20Gi` creates a retained tenant PVC using the default StorageClass; `storageClass` selects a platform-provided class and `existingClaim` uses an existing tenant claim. The portable chart's PVC and Atelier keep policies remain enabled. A namespace deletion is still destructive and is not part of package uninstall.

If the platform offers object storage, create a separate Bucket application in the same tenant and give Mnemosyne that bucket's assigned name, HTTPS endpoint and `<bucket-release>-<user>-credentials` Secret reference under `s3`. The default key names `accessKey` and `secretKey` match Cozystack's projected credentials Secret (not the raw COSI `BucketInfo` JSON). The chart neither looks up nor exports Secret data. The bucket must finish provisioning first; its provider and credential rotation lifecycle remain with the Bucket application. Optional custom field names support other S3 providers.

The default object prefix is `<tenant-namespace>/<app-release>` so different tenants and ateliers do not overwrite one another. S3 mirrors verified publication; the retained PVC still holds drafts and failed attempts. Without a bucket all work stays on the PVC. No bucket is automatically created or deleted. Live S3, storage provisioning and dashboard behavior require platform integration testing; local rendering alone does not establish them.

Backup covers declared namespaced API objects, not the platform, sibling tenants, PVC bytes or Secret contents. The collector adds a minimal namespace identity for restore; it cannot read tenant namespace labels without cluster permissions. Review restoration into a Cozystack tenant rather than applying that identity over platform-managed tenant metadata.
