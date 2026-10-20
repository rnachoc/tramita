# ADR 0006: RustFS as the local S3-compatible object store instead of MinIO

- Status: accepted
- Date: 2026-10-20

## Context

Claim documents (PDFs, scans, photos) are stored in an S3-compatible object store. The original
plan named MinIO. When the local stack was first started in CI, pulling `minio/minio` failed with
"repository does not exist". MinIO stopped publishing community images in October 2025, the last
published image carried a known high-severity vulnerability, and the upstream community repository
has since been archived. Using it would mean building an unmaintained server from source.

## Options considered

1. **Build MinIO from source** and pin our own image. Works, but ships unmaintained software with
   known vulnerabilities in a project that claims "security from the first commit".
2. **Third-party MinIO rebuilds** (hardened-image vendors). Their availability has itself been
   unstable (one vendor announced its registry shutdown for October 2026), and free tiers usually
   only offer a floating `latest` tag.
3. **Garage.** Mature and lightweight, but needs a cluster layout to be assigned after start-up,
   which adds an init job to Compose and Helm.
4. **SeaweedFS.** Capable, but its S3 credentials are configured through a JSON identities file,
   and it is a larger system than this use case needs.
5. **RustFS.** Apache-2.0, S3-compatible, single container, configured with environment variables
   in the same way MinIO was, with releases published several times a week.

## Decision

Option 5, pinned to `rustfs/rustfs:1.0.3` for local development and the kind cluster.

The services only speak the S3 API (boto3 with a configurable endpoint) and read
`S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` and `S3_BUCKET`. Nothing in the code is specific to
RustFS, so pointing the same build at AWS S3, Garage or another backend is a configuration change.

## Consequences

- The stack starts from public, maintained images only.
- RustFS is younger than MinIO. The risk is contained because only basic S3 operations are used
  (put, get, head, list, create bucket), and the CI smoke test exercises them on every push.
- Environment variables were renamed from `MINIO_*` to the backend-neutral `S3_*`.
