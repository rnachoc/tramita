"""Builds claim forms and their documents from plans."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from faker import Faker

from tramita_datagen import content
from tramita_datagen.catalog import Catalog, Line, RequiredDocument
from tramita_datagen.models import (
    AccidentReport,
    ClaimForm,
    Document,
    DocumentFormat,
    DocumentType,
    LineItem,
    Party,
    PoliceReport,
    Policyholder,
    RepairDocument,
)
from tramita_datagen.people import cif, plate
from tramita_datagen.planning import Plan
from tramita_datagen.util import TAX_FACTOR, TAX_RATE, money, require

SCAN_SHARE = 0.25  # share of documents delivered as scanned images
CLAIMED_AMOUNT_SHARE = 0.8  # share of claim forms where the policyholder states an amount
REPAIR_DOCUMENT_SHAPES = {"invoice": 60, "estimate": 25, "both": 15}


def _customer(holder: Policyholder) -> Party:
    address = holder.address
    return Party(
        name=holder.full_name,
        tax_id=holder.nif,
        address=f"{address.street}, {address.postal_code} {address.city}",
    )


class DocumentBuilder:
    def __init__(
        self,
        rng: random.Random,
        faker: Faker,
        catalog: Catalog,
        holders: list[Policyholder],
    ) -> None:
        self.rng = rng
        self.faker = faker
        self.catalog = catalog
        self.holders = {h.holder_id: h for h in holders}
        self._counter = 0

    # ------------------------------------------------------------- amounts

    def _items(self, plan: Plan) -> list[LineItem]:
        rng = self.rng
        if plan.description_mismatch:
            pool = content.MISMATCH_ITEMS[plan.coverage]
            specs = rng.sample(pool, k=min(len(pool), 2))
        else:
            specs = list(plan.story.items)
        items = []
        for spec in specs:
            qty = Decimal(rng.randint(spec.min_qty, spec.max_qty))
            price = money(rng.uniform(spec.min_price, spec.max_price))
            items.append(
                LineItem(
                    description=spec.description,
                    quantity=qty,
                    unit_price=price,
                    amount=money(qty * price),
                )
            )
        # Scale prices so the total lands on the planned target.
        subtotal = sum((i.amount for i in items), Decimal(0))
        factor = Decimal(str(plan.target_total)) / (subtotal * TAX_FACTOR)
        for item in items:
            item.unit_price = money(item.unit_price * factor)
            if plan.round_amounts:
                item.unit_price = Decimal(max(50, int(item.unit_price / 50) * 50))
            item.amount = money(item.quantity * item.unit_price)
        if plan.adjust == "unrelated":
            spec = rng.choice(content.UNRELATED_ITEMS[plan.coverage])
            price = money(rng.uniform(spec.min_price, spec.max_price))
            items.append(
                LineItem(
                    description=spec.description,
                    quantity=Decimal(1),
                    unit_price=price,
                    amount=price,
                    related_to_claim=False,
                )
            )
        if plan.description_mismatch:
            for item in items:
                item.related_to_claim = False
        return items

    def _repair(
        self, plan: Plan, holder: Policyholder, *, kind: DocumentType, issue: date
    ) -> RepairDocument:
        rng = self.rng
        trade = rng.choice(content.TRADES[plan.coverage])
        issuer = Party(
            name=f"{trade} {self.faker.last_name()} S.L.",
            tax_id=cif(rng),
            address=f"{self.faker.street_name()}, {rng.randint(1, 90)}, {self.faker.postcode()} {self.faker.city()}",
        )
        items = self._items(plan)
        subtotal = sum((i.amount for i in items), Decimal(0))
        tax = money(subtotal * TAX_RATE / 100)
        total = subtotal + tax
        if plan.adjust == "inflated":
            # The stated total does not match the sum of the lines plus tax.
            total = money(total * Decimal(str(round(rng.uniform(1.12, 1.30), 2))))
        prefix = "F" if kind is DocumentType.INVOICE else "P"
        return RepairDocument(
            number=f"{prefix}{issue.year}-{rng.randint(100, 9999):04d}",
            issue_date=issue,
            issuer=issuer,
            customer=_customer(holder),
            items=items,
            subtotal=subtotal,
            tax_rate=TAX_RATE,
            tax_amount=tax,
            total=total,
        )

    # ------------------------------------------------------------- documents

    def _document_dates(self, plan: Plan) -> tuple[date, date]:
        """Dates of (report or estimate, invoice). Planted fraud dates them before the incident."""
        if plan.documents_before_incident:
            before = plan.incident - timedelta(days=self.rng.randint(4, 25))
            return before, before + timedelta(days=self.rng.randint(1, 3))
        first = plan.incident + timedelta(days=self.rng.randint(0, 2))
        second = min(plan.reported, first + timedelta(days=self.rng.randint(1, 6)))
        return first, max(first, second)

    def _add(self, plan: Plan, doc_type: DocumentType, **payload: object) -> Document:
        self._counter += 1
        fmt = DocumentFormat.SCAN if self.rng.random() < SCAN_SHARE else DocumentFormat.PDF
        if plan.injection_target == "scan" and doc_type in {
            DocumentType.INVOICE,
            DocumentType.ESTIMATE,
        }:
            fmt = DocumentFormat.SCAN
        document_id = f"DOC-{self._counter:06d}"
        extension = "jpg" if fmt is DocumentFormat.SCAN else "pdf"
        doc = Document.model_validate(
            {
                "document_id": document_id,
                "claim_id": plan.claim_id,
                "document_type": doc_type,
                "format": fmt,
                "filename": f"{document_id}-{doc_type.value.lower().replace('_', '-')}.{extension}",
                **payload,
            }
        )
        plan.documents.append(doc)
        return doc

    def _repair_documents(
        self, plan: Plan, holder: Policyholder, first: date, invoice_date: date
    ) -> None:
        if plan.duplicate_of is not None:
            source = require(plan.duplicate_of.repair_document, "source invoice")
            repair = source.model_copy(deep=True)
            repair.customer = _customer(holder)
            plan.repair_document = repair
            self._add(plan, DocumentType.INVOICE, repair=repair)
            return
        shape = self.rng.choices(
            list(REPAIR_DOCUMENT_SHAPES), weights=list(REPAIR_DOCUMENT_SHAPES.values())
        )[0]
        estimate = None
        if shape in {"estimate", "both"}:
            estimate = self._repair(plan, holder, kind=DocumentType.ESTIMATE, issue=first)
            plan.repair_document = estimate
            self._add(plan, DocumentType.ESTIMATE, repair=estimate)
        if shape in {"invoice", "both"}:
            invoice = self._repair(plan, holder, kind=DocumentType.INVOICE, issue=invoice_date)
            if estimate is not None:
                # The final invoice repeats the accepted estimate.
                invoice.items = [i.model_copy() for i in estimate.items]
                invoice.subtotal, invoice.tax_amount, invoice.total = (
                    estimate.subtotal,
                    estimate.tax_amount,
                    estimate.total,
                )
            plan.repair_document = invoice
            self._add(plan, DocumentType.INVOICE, repair=invoice)

    def _police_report(self, plan: Plan, holder: Policyholder, filed: date) -> PoliceReport:
        alcohol = plan.exclusion == "AUTO_ALCOHOL"
        if alcohol:
            vehicle = require(plan.policy.vehicle, "vehicle")
            narrative = (
                "Los agentes instructores hacen constar que el conductor del vehículo con matrícula "
                f"{vehicle.plate} colisionó con un vehículo estacionado y, sometido a la prueba de "
                "detección de alcohol, arrojó un resultado positivo."
            )
        else:
            narrative = f"El compareciente manifiesta que {plan.description[0].lower()}{plan.description[1:]}"
        return PoliceReport(
            report_number=f"{'AT' if alcohol else 'DEN'}-{plan.incident.year}-{self.rng.randint(10000, 99999)}",
            station=f"Comisaría de Distrito de {self.faker.city()} (ficticia)",
            filed_date=filed,
            incident_date=plan.incident,
            complainant=Party(
                name=holder.full_name,
                tax_id=holder.nif,
                address=f"{holder.address.street}, {holder.address.city}",
            ),
            complainant_phone=holder.phone,
            narrative=narrative,
            stolen_items=[] if alcohol else list(plan.story.stolen),
            forced_entry=not alcohol
            and plan.exclusion not in {"THEFT_WITHOUT_FORCE", "AUTO_THEFT_KEYS"},
            alcohol_test_mg_l=money(self.rng.uniform(0.38, 0.72)) if alcohol else None,
        )

    def _accident_report(
        self, plan: Plan, holder: Policyholder, report_date: date
    ) -> AccidentReport:
        vehicle = require(plan.policy.vehicle, "vehicle")
        other = plan.story.other_vehicle
        other_name = f"{self.faker.first_name()} {self.faker.last_name()} {self.faker.last_name()}"
        return AccidentReport(
            report_date=report_date,
            incident_date=plan.incident,
            location=f"{self.faker.street_name()}, {self.faker.city()}",
            driver_a=Party(name=holder.full_name, tax_id=holder.nif),
            plate_a=vehicle.plate,
            insurer_a=self.catalog.insurer.name,
            driver_b=Party(name=other_name, tax_id="(no consta)") if other else None,
            plate_b=plate(self.rng) if other else None,
            insurer_b=self.rng.choice(content.OTHER_INSURERS) if other else None,
            circumstances=plan.story.circumstances
            or "Colisión del vehículo A según la descripción del asegurado.",
        )

    def _location(self, plan: Plan, holder: Policyholder) -> str:
        if plan.policy.line is Line.HOME:
            address = plan.policy.insured_address or holder.address
            return f"{address.street}, {address.postal_code} {address.city}"
        return f"{self.faker.street_name()}, {self.faker.city()}"

    # ------------------------------------------------------------- claims

    def build(self, plans: list[Plan]) -> tuple[list[ClaimForm], list[Document]]:
        claims: list[ClaimForm] = []
        documents: list[Document] = []
        for plan in plans:
            holder = self.holders[plan.policy.holder_id]
            required = set(self.catalog.coverages[plan.coverage].required_documents)
            if plan.missing:
                required.discard(plan.missing)
            first, invoice_date = self._document_dates(plan)
            alcohol = plan.exclusion == "AUTO_ALCOHOL"

            if RequiredDocument.POLICE_REPORT in required or alcohol:
                self._add(
                    plan,
                    DocumentType.POLICE_REPORT,
                    police_report=self._police_report(plan, holder, first),
                )
            if RequiredDocument.ACCIDENT_REPORT in required and not alcohol:
                self._add(
                    plan,
                    DocumentType.ACCIDENT_REPORT,
                    accident_report=self._accident_report(plan, holder, first),
                )
            if RequiredDocument.REPAIR_INVOICE_OR_ESTIMATE in required:
                self._repair_documents(plan, holder, first, invoice_date)

            description = plan.description
            if plan.injection and plan.injection_target == "description":
                description = f"{description} {plan.injection}"
            elif plan.injection:
                repairs = [d for d in plan.documents if d.repair is not None]
                (repairs or plan.documents)[-1].injected_instruction = plan.injection

            stated = plan.repair_document.total if plan.repair_document else None
            claims.append(
                ClaimForm(
                    claim_id=plan.claim_id,
                    policy_number=plan.policy.policy_number,
                    reported_date=plan.reported,
                    incident_date=plan.incident,
                    claim_type=plan.coverage,
                    location=self._location(plan, holder),
                    description=description,
                    claimed_amount=stated if self.rng.random() < CLAIMED_AMOUNT_SHARE else None,
                    contact_phone=holder.phone,
                    contact_email=holder.email,
                    document_ids=[d.document_id for d in plan.documents],
                )
            )
            documents.extend(plan.documents)
        return claims, documents
