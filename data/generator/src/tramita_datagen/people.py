"""Policyholders and policies.

Identifiers have valid formats and check digits so PII detection can be tested
realistically. IBANs use bank code 9999, which no Spanish bank uses, and e-mail
addresses use the reserved ``.example`` domain.
"""

from __future__ import annotations

import random
import unicodedata
from datetime import date, timedelta
from decimal import Decimal

from faker import Faker

from tramita_datagen.catalog import Catalog, Line
from tramita_datagen.content import VEHICLES
from tramita_datagen.models import Address, Policy, Policyholder, Vehicle

_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_PLATE_LETTERS = "BCDFGHJKLMNPRSTVWXYZ"

HOME_PRODUCTS = {"HB": 0.30, "HP": 0.45, "HT": 0.25}
AUTO_PRODUCTS = {"AT": 0.20, "AA": 0.25, "AF": 0.30, "AR": 0.25}
HOME_ONLY_SHARE = 0.55  # policyholders with only a home policy
AUTO_ONLY_SHARE = 0.30  # policyholders with only a car policy; the rest have both
OWN_HOME_SHARE = 0.85  # home policies that insure the holder's own address
PREMIUMS = {"HB": 140, "HP": 230, "HT": 390, "AT": 260, "AA": 340, "AF": 520, "AR": 760}


def nif(rng: random.Random) -> str:
    number = rng.randint(10_000_000, 79_999_999)
    return f"{number}{_NIF_LETTERS[number % 23]}"


def cif(rng: random.Random) -> str:
    """Company tax id (CIF) for a limited company, with its control digit."""
    digits = [rng.randint(0, 9) for _ in range(7)]
    even = sum(digits[1::2])
    odd = sum(sum(divmod(d * 2, 10)) for d in digits[0::2])
    control = (10 - (even + odd) % 10) % 10
    return "B" + "".join(map(str, digits)) + str(control)


def iban(rng: random.Random) -> str:
    """Spanish IBAN with a valid checksum and the unused bank code 9999."""
    bban = (
        "9999"
        + f"{rng.randint(0, 9999):04d}"
        + f"{rng.randint(0, 99):02d}"
        + f"{rng.randint(0, 10**10 - 1):010d}"
    )
    numeric = bban + "142800"  # "ES" -> 14 28, followed by "00"
    check = 98 - int(numeric) % 97
    raw = f"ES{check:02d}{bban}"
    return " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def plate(rng: random.Random) -> str:
    return f"{rng.randint(0, 9999):04d} " + "".join(rng.choice(_PLATE_LETTERS) for _ in range(3))


def _ascii(text: str) -> str:
    normalised = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalised if c.isascii() and (c.isalnum() or c == " ")).lower()


def _pick(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


class PeopleFactory:
    def __init__(
        self, rng: random.Random, faker: Faker, catalog: Catalog, reference_date: date
    ) -> None:
        self.rng = rng
        self.faker = faker
        self.catalog = catalog
        self.reference_date = reference_date

    def address(self) -> Address:
        f = self.faker
        return Address(
            street=f"{f.street_name()}, {self.rng.randint(1, 140)}, {self.rng.randint(1, 8)}º {self.rng.choice('ABCD')}",
            postal_code=f.postcode(),
            city=f.city(),
            province=f.state(),
        )

    def policyholder(self, index: int) -> Policyholder:
        first = self.faker.first_name()
        last = f"{self.faker.last_name()} {self.faker.last_name()}"
        handle = _ascii(f"{first}.{last.split(maxsplit=1)[0]}").replace(" ", "")
        return Policyholder(
            holder_id=f"PH-{index:04d}",
            full_name=f"{first} {last}",
            nif=nif(self.rng),
            birth_date=self.reference_date - timedelta(days=self.rng.randint(22 * 365, 78 * 365)),
            email=f"{handle}{self.rng.randint(1, 99)}@correo.example",
            phone=f"+34 6{self.rng.randint(0, 99):02d} {self.rng.randint(0, 999):03d} {self.rng.randint(0, 999):03d}",
            address=self.address(),
            iban=iban(self.rng),
        )

    def policy(self, number: int, holder: Policyholder, line: Line) -> Policy:
        product = _pick(self.rng, HOME_PRODUCTS if line is Line.HOME else AUTO_PRODUCTS)
        # Every policy is in force on the reference date; start dates spread over the previous year.
        start = self.reference_date - timedelta(days=self.rng.randint(40, 360))
        premium = Decimal(PREMIUMS[product]) * Decimal(str(round(self.rng.uniform(0.85, 1.25), 2)))
        policy = Policy(
            policy_number=f"BR-{product}-{number:06d}",
            holder_id=holder.holder_id,
            product_code=product,
            line=line,
            start_date=start,
            end_date=start + timedelta(days=364),
            annual_premium=premium.quantize(Decimal("0.01")),
        )
        if line is Line.HOME:
            policy.insured_address = (
                holder.address if self.rng.random() < OWN_HOME_SHARE else self.address()
            )
        else:
            make, model = self.rng.choice(VEHICLES)
            policy.vehicle = Vehicle(
                plate=plate(self.rng),
                make=make,
                model=model,
                year=self.rng.randint(2012, 2026),
            )
            policy.insured_value = Decimal(self.rng.randrange(6000, 28000, 500))
        return policy

    def build(self, holders: int) -> tuple[list[Policyholder], list[Policy]]:
        people = [self.policyholder(i + 1) for i in range(holders)]
        policies: list[Policy] = []
        for holder in people:
            roll = self.rng.random()
            lines = (
                [Line.HOME]
                if roll < HOME_ONLY_SHARE
                else [Line.AUTO]
                if roll < HOME_ONLY_SHARE + AUTO_ONLY_SHARE
                else [Line.HOME, Line.AUTO]
            )
            for line in lines:
                policies.append(self.policy(len(policies) + 1, holder, line))
        return people, policies
