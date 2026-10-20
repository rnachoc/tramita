"""Typed view of data/policies/catalog.yaml, the product catalog."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPO_ROOT / "data" / "policies" / "catalog.yaml"


class Line(StrEnum):
    HOME = "HOME"
    AUTO = "AUTO"


class CoverageCode(StrEnum):
    HOME_WATER = "HOME_WATER"
    HOME_THEFT = "HOME_THEFT"
    HOME_GLASS = "HOME_GLASS"
    AUTO_COLLISION = "AUTO_COLLISION"
    AUTO_GLASS = "AUTO_GLASS"
    AUTO_THEFT = "AUTO_THEFT"


class RequiredDocument(StrEnum):
    REPAIR_INVOICE_OR_ESTIMATE = "REPAIR_INVOICE_OR_ESTIMATE"
    POLICE_REPORT = "POLICE_REPORT"
    ACCIDENT_REPORT = "ACCIDENT_REPORT"


class FraudSignalType(StrEnum):
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    DATE_INCONSISTENCY = "DATE_INCONSISTENCY"
    DESCRIPTION_MISMATCH = "DESCRIPTION_MISMATCH"
    EARLY_CLAIM = "EARLY_CLAIM"
    FREQUENT_CLAIMS = "FREQUENT_CLAIMS"
    ROUND_AMOUNTS = "ROUND_AMOUNTS"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Insurer(_Frozen):
    name: str
    legal_notice: str


class FraudRules(_Frozen):
    review_threshold: float
    investigation_threshold: float
    weights: dict[FraudSignalType, float]
    early_claim_days: int
    frequent_claims_window_days: int
    frequent_claims_min: int


class Operations(_Frozen):
    review_threshold_eur: int
    notice_days: int
    fraud: FraudRules


class Exclusion(_Frozen):
    code: str
    text: str


class Coverage(_Frozen):
    line: Line
    title: str
    description: str
    exclusions: tuple[Exclusion, ...]
    required_documents: tuple[RequiredDocument, ...]


class Guarantee(_Frozen):
    limit: int | Literal["insured_value"]
    deductible: int
    waiting_days: int


class Product(_Frozen):
    name: str
    line: Line
    guarantees: dict[CoverageCode, Guarantee]


class Catalog(_Frozen):
    insurer: Insurer
    operations: Operations
    coverages: dict[CoverageCode, Coverage]
    documents: dict[RequiredDocument, str]
    products: dict[str, Product]

    def product(self, code: str) -> Product:
        return self.products[code]


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    with path.open(encoding="utf-8") as handle:
        return Catalog.model_validate(yaml.safe_load(handle))
