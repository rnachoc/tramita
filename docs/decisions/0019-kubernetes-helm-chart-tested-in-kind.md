# ADR 0019: One Helm chart, hardened pods, deny-by-default networking, tested in kind

- Status: accepted
- Date: 2026-11-17

## Context

Docker Compose runs the infrastructure for development, with the services on the host. The brief
asks for Kubernetes: the same system as deployable units, with the trust boundaries of the design
(ADRs 0002, 0009, 0015) enforced by the platform too, and testable without a cloud account.

## Options considered

**Packaging.** Raw manifests with Kustomize overlays, or a Helm chart.

**Infrastructure.** Third-party charts for PostgreSQL, Kafka, OpenSearch and Temporal; operators;
or minimal single-replica manifests with the Compose images, switchable off for managed services.

**Testing.** Render and lint only; or install into a real cluster in CI and test there.

## Decision

- **A Helm chart** (`deploy/helm/tramita`): the core, the agents' API, worker and bridge, the
  review console, a job that indexes the policy conditions, and optional development-grade
  infrastructure (`infrastructure.enabled`) with the same images as Compose. Third-party charts
  were left out: the widely used ones moved their images behind a subscription in 2025, and
  operators are more than a single-replica development stack needs.
- **Images** for the core and the agents, multi-stage, non-root (uid 10001), able to run with a
  read-only root file system and `/tmp` as the only writable path.
- **Pod hardening**: `runAsNonRoot`, read-only root file system, all capabilities dropped,
  `RuntimeDefault` seccomp, no service account token. Infrastructure pods run non-root where
  their images allow (PostgreSQL as 999, Kafka and OpenSearch as 1000).
- **Secrets** generated at install time with `randAlphaNum` and read back with `lookup` on
  upgrade, so they never appear in values or in the repository and do not change under a running
  system.
- **Network policies**: ingress denied to every pod of the release, then allowed per component
  (the core from the agents and the console; the database from the core, the agents, the index
  job and Temporal; OpenSearch from the agents; Kafka from the core and the bridge). Egress stays
  open: the index job downloads the search models and the agents may call the model provider.
- **OpenSearch's security plugin is off**, as in Compose: it holds only the public policy
  conditions, and only the agent pods can reach it. Production would enable it with real
  certificates.
- **Tested in a cluster**: `helm test` runs two pods. One generates the synthetic dataset, seeds
  the core, ingests and analyses a sample of claims through the cluster's services and checks
  that none is left unanalysed; the other, with no allowed role, must reach the console and
  nothing else. CI lints the chart, validates the rendered manifests with kubeconform against the
  Kubernetes 1.34 schemas, and installs and tests the chart on kind.

## Consequences

- Verified locally on kind (Kubernetes 1.37): every pod ready, the index built, 12 claims analysed
  inside the cluster, and the network policies enforced (kindnet enforces them).
- The infrastructure is single replica with no backups: fine for development and demos, not for
  production, where the services would point at managed PostgreSQL, Kafka and OpenSearch.
- The search models live on a ReadWriteOnce volume shared by the pods on one node; several nodes
  would need ReadWriteMany storage or a model per pod.
- No ingress controller, TLS or OIDC in the chart: the console is reached with a port-forward,
  and reviewers are still not individually authenticated (ADR 0015).
- The agents image is about 1.4 GB (spaCy, Presidio, ONNX Runtime); building and loading it is
  most of the CI job's time.
