# Kubernetes state carried by works

`collect.py` uses Kubernetes Python client 37 API discovery, including custom
and aggregated API groups. It selects the preferred served version per resource,
falling back to other served versions for resources absent from the preferred
version. Only resources advertising list and create are backup candidates;
read-only metrics are not restore objects. GET is the only HTTP method used.
Pagination is followed; any discovery/list failure aborts without an archive.

With `--namespace`, only namespaced resource endpoints in that namespace are
read. No Namespace object, CRD, PV, cluster RBAC, other tenant, or core Secret is
read. Global API discovery still runs. Omit `--namespace` for a full-cluster
API-object snapshot on a cluster where that access is authorized.

Secrets are excluded before requests. As a conservative extension this also
excludes custom kinds containing `secret` (e.g. TenantSecret, ExternalSecret).
`--include-secrets` includes them in both collection and manifest conversion;
never use it on workshop. Application manifests may themselves contain inline
credentials. Archive, key and package files are created mode 0600, exclusively;
existing output is not replaced.

Events, leases, endpoints/slices, controller-owned Pods and Deployment-owned
ReplicaSets are excluded. Top-level status and server metadata are removed,
as is the last-applied annotation (which can duplicate stale server fields).
Native PodTemplate metadata is normalized too. Application dictionaries inside
ConfigMaps and CR specs are preserved. OwnerReferences retain their original
UIDs as relationship evidence; a future restore must resolve names to new UIDs.

Canonicalization sorts YAML keys and tar member paths, uses fixed USTAR headers
and zstd with checksum. Member paths are SHA-256 of API version/kind/namespace/
name; object identity remains in each YAML document. Same logical input and
pinned dependency versions produce identical archive bytes, regardless of list
order. A live snapshot is not atomic across different resource lists.

This is API desired-state backup, not etcd, volume contents, external databases,
images, or a complete restore executor. Restore still needs dependency ordering
(CRDs, namespaces, RBAC, workloads), owner-reference and PV binding reconciliation,
and handling of finalizers, allocated Service addresses and environment-specific
fields. Namespace-only backups need their cluster-scoped prerequisites supplied
separately. The encrypted archive limit inherited from `weave.payload` is 16 MiB.

## Reproduce

Run in the repository. Choose new output paths for subsequent runs.

```sh
uv run python -m scheherazade.state.collect \
  --kubeconfig ~/workshop.txt --context admin@workshop \
  --namespace tenant-scheherazade --output out/state-backup/new-workshop.tar.zst
uv run python hack/restore/state_manifests.py shop 2025-07-01T00:00:00+00:00 > /tmp/shop-state.yaml
uv run python -m scheherazade.state.collect \
  --manifests /tmp/shop-state.yaml --output out/state-backup/new-synthetic.tar.zst
uv run python -m scheherazade.weave.backup pack out/state-backup/new-workshop.tar.zst \
  --output out/state-backup/new-frames --key out/state-backup/recipient.key --capacity 512
uv run python -m scheherazade.weave.backup check-loss out/state-backup/new-frames \
  --archive out/state-backup/new-workshop.tar.zst --key out/state-backup/recipient.key
# Pass surviving per-work directories; neither original archive, external
# catalogue.json nor envelope.bin is used by recover:
uv run python -m scheherazade.weave.backup recover out/state-backup/new-frames/0* \
  --key out/state-backup/recipient.key --output out/state-backup/recovered.tar.zst
uv run python -m unittest discover -s tests -p 'test_state*.py' -v
uv run python -m unittest discover -s tests -p 'test_weave*.py' -v
```

## Fountain and catalogue contract

`weave.fountain` is a systematic dense random-linear GF(2) fountain reference
implementation. It is not RaptorQ or sparse LT: it trades CPU/memory for a simple
Gaussian decoder. K is limited to 4096 source blocks; large workloads belong in
studio pods. `payload.seal` runs once. All repair frames are XORs of encrypted
blocks; no plaintext shards or repeated encryption. Frame indices 0..K-1 are
systematic, subsequent uint64 indices generate repair equations using SHAKE256.
Any subset with full rank reconstructs. K+32 independent equations have rank
failure probability below 2^-32 in the random-oracle model; arbitrary adversarial
subsets are not guaranteed. A rank-deficient decoder fails without plaintext;
request more repair indices from the saved envelope with `fountain.Encoder`.

Each fixed-size frame has 88 bytes overhead: magic/version, full 32-byte
ciphertext snapshot hash, uint64 index, K, block size, envelope size, HMAC-SHA256.
HMAC covers the complete header and equation; final recovery verifies the
snapshot hash and envelope AEAD. As in existing weave, the encoder requires the
recipient private key for frame authentication; this is not an owner signature.
Mixed snapshots/dimensions, corruption, inconsistent equations and incomplete
rank fail closed. Duplicate frames add no rank. Defaults allocate
ceil((K+32)/0.7) works, one frame each. Loss checks omit ceil(30% of N) works
without deleting any files.

`--capacity` is the measured capacity of the intended art carrier including the
88-byte frame overhead; 512 is a transport test size, not a claim about any
particular score. `--work-ids` accepts a JSON array of actual distinct work IDs;
without it, IDs are explicitly pending work slots. Every package contains
`frame.bin` and `metadata.json`, with a complete compact authenticated catalogue
replicated under `backup.catalogue`. Catalogue `works[i]` maps frame index to work
ID; shared snapshot/codec/dimensions are stored once. Metadata has its own size
budget, separate from the carrier frame. Catalogue size is linear in work count.
`catalogue.metadata` merges into existing work metadata without changing it.

These are carrier-ready packages. No new art is generated or existing works
rewritten by this CLI. A carrier adapter stores frame bytes in its approved
surface (e.g. `surface.encode` for an exactly matching MusicXML capacity) and
copies the supplied backup metadata into the work's metadata. Existing v1
`frames.py`/nocturne wire formats remain unchanged. Artistic capacity/choice
approval is separate from this tested state-to-frame transport.
