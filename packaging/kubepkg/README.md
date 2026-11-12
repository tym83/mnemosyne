# Kuberoot package through kubepkg

The recipe uses the portable Helm chart; it introduces no Kuberoot API dependency into the core. `prepare.py` copies the chart from this repository into the recipe's `charts/mnemosyne` source, because kubepkg deliberately forbids `dir: ../../charts/...` escaping a recipe. The result is self-contained and can later be submitted to kubepkg-recipes. No checkout there is modified.

## Catalog check versus release

The checked-in recipe is a staging recipe, **not a finished published release**. Images have not yet been built by Actions in this workspace. With no release inputs, preparation creates an inactive catalog containing all ten CRDs and the model ConfigMap. This validates packaging without inventing image digests. `readyWhen` waits for every CRD's `Established` condition; this does not claim that an atelier controller runs.

```sh
uv run python packaging/prepare.py --output out/packages-catalog
kubepkg validate out/packages-catalog/kubepkg
kubepkg build out/packages-catalog/kubepkg --work-dir out/packages-catalog/build
```

For the executable package, first run the repository's Mnemosyne images workflow after review. It builds `containers/Containerfile` from this repository and emits controller/studio digest values plus image SBOM and provenance attestations. Heavy image building stays in Actions. Use the matching reviewed source revision for both chart preparation and images. Supply owner values with `addon.enabled: true`, the atelier key **reference** and the owner's public key, `addon.suspend: true` during installation checks, private image-pull references, and the mode (chamber, or background with explicitly configured models). Never put raw keys or tokens in values.

```sh
uv run python packaging/prepare.py --release --output out/packages-release \
  --values controller.yaml --values studio.yaml --values owner.yaml
kubepkg validate out/packages-release/kubepkg
kubepkg build out/packages-release/kubepkg --work-dir out/packages-release/build
```

Release preparation rejects missing/malformed digests and renders the enabled core chart before declaring success. It writes both controller and studio references into `package.images`: the studio lives inside a runtime ConfigMap and starts later as a Job, so chart image discovery alone would miss it. The controller's `Available` condition is added to `readyWhen`. Availability is installation health, not proof that composition, backup or recovery has succeeded. Image existence and attestations still need verification against the Actions artifacts; a syntactically valid digest is not evidence of a successful build.

The release output includes site-specific non-secret references from owner values. Keep it private, or move those settings into the target Package's component values before distribution. Public recipe submissions must carry genuine immutable release pins and no site credentials. Keep the self-contained staged source and SHA-256 manifest with the release. Changes to published content require incrementing `PACKAGE_BUILD` in `packaging/generate.py` and regenerating `spec.build`; version `0.2.0` follows the core chart. CRD upgrades use `CreateReplace`; `rollback.safe: false` avoids silently downgrading retained record schemas.

## Publish, sign and produce the package SBOM

Publishing is an explicit maintainer step; local checks never push:

```sh
kubepkg build out/packages-release/kubepkg \
  --registry oci://REGISTRY/PRIVATE-PACKAGES -o out/packages-release/dist
kubepkg repo index out/packages-release/dist -o out/packages-release/index.yaml \
  --sign-key-env KUBEPKG_SIGNING_KEY
# Serve index.yaml AND index.yaml.sig, then use the already-trusted public key:
kubepkg sbom mnemosyne --repo https://PACKAGES/index.yaml \
  --public-key release.pub -o out/packages-release/mnemosyne.cdx.json
```

Use `--merge https://PACKAGES/index.yaml` on later indexes to retain published versions. Keep the signing key outside this repository. The signed index pins the chart artifacts; `package.images` pins all container images, including the deferred studio. CycloneDX 1.6 from `kubepkg sbom` describes the package, charts, images and dependency graph. The image-build SBOM attestations describe image contents: neither replaces the other. No image-signature rule is fabricated; add `spec.verify.images` only once the release workflow actually signs images with a reviewed identity/key.

## Install check in a disposable kind cluster

Use a Linux test runner with kind and Podman/nerdctl (or an explicitly chosen working Docker daemon), kubectl, Helm and kubepkg. Supply a published, signed index and a reviewed operator chart version. This creates a fresh cluster, installs the actual kubepkg operator, verifies the signed repository, installs Mnemosyne through kubepkg, waits for Package Ready and writes the cluster SBOM. It never uses the current kubeconfig or contacts workshop.

```sh
uv run python packaging/kubepkg/kind_check.py \
  --provider podman --operator-version REVIEWED_VERSION \
  --index https://PACKAGES/index.yaml --public-key release.pub \
  --output out/kind-package-new
```

The default check explicitly reports **inactive catalog**. Use `--active` with an executable package only after arranging the atelier key and private registry credentials in that fresh cluster; those are not read, generated or printed by this script. Keep work suspended for installation-only checks. Cluster and evidence are retained on success and failure; remove the named test cluster manually only after reviewing evidence. This check does not perform an artistic run or a backup recovery test; use the separate core add-on e2e for that.

To exercise index signing, chart digest verification and SBOM generation without a container runtime, serve the locally built chart on loopback:

```sh
uv run python packaging/kubepkg/catalog_check.py \
  --recipe out/packages-catalog/kubepkg/recipe.yaml \
  --tree out/packages-catalog/build/tree \
  --output out/catalog-supply-chain-new
```

This retains an ephemeral test signing key outside the HTTP-served directory, verifies the actual chart archive, and produces `catalog.cdx.json`. It does not publish an OCI artifact or claim an operator installation. Its index contains temporary localhost URLs and is not a release index.
