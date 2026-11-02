"""End-to-end check of document reading against the running stack and core (used by CI).

Ingests a sample of the generated claims twice with ``tramita-ingest`` (keyless: the fake model),
then verifies through the core API and the object store that every document was stored intact,
registered with its true type and recorded with an extraction that holds no personal data.
The sample always includes scans and documents with planted instructions. Unlike the ingest
itself, this check reads the dataset's ground truth, to compare against it.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import boto3

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "generated"
CORE = os.environ.get("TRAMITA_CORE_URL", "http://localhost:8080").rstrip("/")


def fail(message: str) -> None:
    print(f"  FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def key(role: str) -> str:
    for entry in os.environ["TRAMITA_API_KEYS"].split(";"):
        parts = entry.strip().split(":", 2)
        if len(parts) == 3 and parts[1] == role:  # noqa: PLR2004
            return parts[2]
    raise SystemExit(f"no {role} key")


def get(path: str) -> Any:
    request = urllib.request.Request(CORE + path, headers={"X-Api-Key": key("ANALYST")})  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read())


def sample(documents: list[dict[str, Any]]) -> list[str]:
    claims = list(dict.fromkeys(d["claim_id"] for d in documents))[:5]
    scans = [d["claim_id"] for d in documents if d["format"] == "SCAN"]
    injected = [d["claim_id"] for d in documents if d.get("injected_instruction")]
    return list(dict.fromkeys(claims + scans[:4] + injected[:3]))


def main() -> None:
    documents = json.loads((DATASET / "documents.json").read_text(encoding="utf-8"))
    holders = json.loads((DATASET / "policyholders.json").read_text(encoding="utf-8"))
    chosen = sample(documents)
    for attempt in ("first", "second"):
        run = subprocess.run(  # noqa: S603
            ["uv", "run", "tramita-ingest", "--claims", ",".join(chosen)],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if run.returncode != 0:
            fail(f"{attempt} ingest exited with {run.returncode}: {run.stderr[-800:]}")
        print(f"  ok   {attempt} ingest of {len(chosen)} claims")

    personal = {v for h in holders for v in (h["full_name"], h["nif"], h["email"], h["phone"])}
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name="us-east-1",
    )
    bucket = os.environ.get("S3_BUCKET", "claim-documents")
    truth = {d["document_id"]: d for d in documents}
    checked = scans = instructions = 0
    for claim_id in chosen:
        for doc in get(f"/api/claims/{claim_id}")["documents"]:
            expected = truth[doc["document_id"]]
            if doc["document_type"] != expected["document_type"]:
                fail(f"{doc['document_id']} registered as {doc['document_type']}")
            if not doc["extracted_at"]:
                fail(f"{doc['document_id']} has no extraction")
            original = (DATASET / "documents" / claim_id / expected["filename"]).read_bytes()
            stored = s3.get_object(Bucket=bucket, Key=doc["storage_key"])["Body"].read()
            if hashlib.sha256(stored).digest() != hashlib.sha256(original).digest():
                fail(f"{doc['document_id']} stored bytes differ from the original")
            extraction = json.dumps(doc["extraction"], ensure_ascii=False)
            leaked = [v for v in personal if v in extraction]
            if leaked:
                fail(f"{doc['document_id']} extraction contains personal data")
            found = doc["extraction"]["embedded_instructions"]
            if expected.get("injected_instruction") and expected["format"] == "PDF" and not found:
                fail(f"{doc['document_id']} planted instruction not reported")
            checked += 1
            scans += expected["format"] == "SCAN"
            instructions += bool(found)
    summary = (
        f"{len(chosen)} claims ingested twice; {checked} documents ({scans} scans) stored intact, "
        f"typed and extracted; no personal data in any extraction; {instructions} with "
        "instructions flagged"
    )
    print(f"  ok   {summary}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=ingest check::{summary}")


if __name__ == "__main__":
    main()
