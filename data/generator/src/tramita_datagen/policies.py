"""Renders the policy conditions (Spanish markdown) for every product in the catalog.

Every clause gets a stable identifier such as ``HP-2.1`` (product code, article,
clause). Agents must cite these identifiers, and the expected resolutions in the
eval set refer to them through the semantic keys returned in ``Conditions.index``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tramita_datagen.catalog import Catalog, CoverageCode, Guarantee, Line, Product


@dataclass(frozen=True)
class Clause:
    clause_id: str
    article: str
    title: str
    text: str


@dataclass
class Conditions:
    product_code: str
    product_name: str
    clauses: list[Clause] = field(default_factory=list)
    # Semantic key (for example "exclusion:WATER_MAINTENANCE") -> clause id.
    index: dict[str, str] = field(default_factory=dict)

    def cite(self, key: str) -> str:
        return self.index[key]


def _eur(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " €"


def _clause_item(text: str) -> str:
    """Turns a sentence into an item of an enumeration: lower-case start, no final period."""
    text = " ".join(text.split()).rstrip(".")
    return text[0].lower() + text[1:]


def _limit_text(guarantee: Guarantee) -> str:
    if guarantee.limit == "insured_value":
        return "del valor asegurado del vehículo que figura en las condiciones particulares"
    return f"de {_eur(guarantee.limit)}"


class _Builder:
    def __init__(self, product_code: str, product: Product) -> None:
        self.conditions = Conditions(product_code, product.name)
        self._article_no = 0
        self._article_title = ""
        self._clause_no = 0

    def article(self, title: str) -> None:
        self._article_no += 1
        self._article_title = title
        self._clause_no = 0

    def clause(self, title: str, text: str, *keys: str) -> str:
        self._clause_no += 1
        clause_id = f"{self.conditions.product_code}-{self._article_no}.{self._clause_no}"
        article = f"Artículo {self._article_no}. {self._article_title}"
        self.conditions.clauses.append(Clause(clause_id, article, title, text.strip()))
        for key in keys:
            self.conditions.index[key] = clause_id
        return clause_id


_LINE_COVERAGES = {
    Line.HOME: [CoverageCode.HOME_WATER, CoverageCode.HOME_THEFT, CoverageCode.HOME_GLASS],
    Line.AUTO: [CoverageCode.AUTO_COLLISION, CoverageCode.AUTO_GLASS, CoverageCode.AUTO_THEFT],
}


def build_conditions(catalog: Catalog, product_code: str) -> Conditions:
    product = catalog.product(product_code)
    b = _Builder(product_code, product)
    included = list(product.guarantees)
    not_included = [c for c in _LINE_COVERAGES[product.line] if c not in product.guarantees]

    # Article 1: object and definitions.
    b.article("Objeto del seguro y definiciones")
    subject = "la vivienda asegurada" if product.line is Line.HOME else "el vehículo asegurado"
    b.clause(
        "Objeto del seguro",
        f"""
{catalog.insurer.name} (en adelante, la Aseguradora) se obliga, mediante el cobro de la
prima y dentro de los límites pactados, a indemnizar los daños sufridos por {subject} como
consecuencia de los riesgos expresamente cubiertos en el artículo 2, conforme a la Ley
50/1980, de 8 de octubre, de Contrato de Seguro.
""",
        "object",
    )
    b.clause(
        "Tomador y asegurado",
        """
Tomador es la persona que suscribe el contrato y paga la prima. Asegurado es el titular del
interés expuesto al riesgo. Salvo indicación en contrario de las condiciones particulares,
tomador y asegurado son la misma persona.
""",
    )
    b.clause(
        "Siniestro",
        """
Todo hecho súbito, accidental y ajeno a la voluntad del asegurado cuyas consecuencias estén
cubiertas por alguna de las garantías de la póliza. Se considera un único siniestro el
conjunto de daños derivados de una misma causa.
""",
        "definition:claim",
    )
    b.clause(
        "Franquicia",
        """
Importe que, en cada siniestro, queda a cargo del asegurado y se descuenta de la
indemnización que corresponda.
""",
        "definition:deductible",
    )
    b.clause(
        "Periodo de carencia",
        """
Plazo contado desde la fecha de efecto de la póliza durante el cual los siniestros ocurridos
no están cubiertos por la garantía a la que se aplica.
""",
        "definition:waiting",
    )
    if product.line is Line.HOME:
        b.clause(
            "Continente y contenido",
            """
Continente es el conjunto de elementos constructivos de la vivienda, incluidas sus
instalaciones fijas de agua, gas, electricidad y calefacción. Contenido es el conjunto de
bienes muebles, mobiliario y enseres de uso doméstico que se encuentren en la vivienda.
""",
        )
    else:
        b.clause(
            "Vehículo y valor asegurado",
            """
Vehículo asegurado es el identificado por su matrícula en las condiciones particulares, con
los accesorios de serie. Valor asegurado es el que figura en las condiciones particulares y
constituye el límite máximo de indemnización por daños propios.
""",
        )

    # Article 2: guarantees.
    b.article("Garantías cubiertas")
    if product.line is Line.AUTO:
        b.clause(
            "Responsabilidad civil",
            """
La Aseguradora garantiza la responsabilidad civil de suscripción obligatoria y la
responsabilidad civil voluntaria derivadas de la circulación del vehículo asegurado, frente a
los daños causados a terceros. Los daños sufridos por el propio vehículo solo están
cubiertos cuando la póliza incluye la garantía correspondiente de este artículo.
""",
            "coverage:LIABILITY",
        )
    for code in included:
        coverage = catalog.coverages[code]
        b.clause(coverage.title, coverage.description, f"coverage:{code}")
    if not_included:
        titles = ", ".join(catalog.coverages[c].title.lower() for c in not_included)
        b.clause(
            "Riesgos no incluidos en este producto",
            f"""
El producto {product.name} no incluye las siguientes garantías: {titles}. Los siniestros
derivados de estos riesgos no están cubiertos, salvo contratación de un producto superior.
""",
            *(f"not_included:{c}" for c in not_included),
        )

    # Article 3: exclusions.
    b.article("Exclusiones")
    b.clause(
        "Exclusiones generales",
        """
En ningún caso quedan cubiertos: (a) los siniestros causados intencionadamente por el
asegurado o con su complicidad; (b) los daños derivados de guerra, terrorismo, terremotos,
inundaciones extraordinarias y demás riesgos extraordinarios cuya cobertura corresponde al
Consorcio de Compensación de Seguros; (c) los daños anteriores a la fecha de efecto de la
póliza.
""",
        "exclusion:GENERAL",
    )
    for code in included:
        coverage = catalog.coverages[code]
        items = "; ".join(
            f"({chr(ord('a') + i)}) {_clause_item(exclusion.text)}"
            for i, exclusion in enumerate(coverage.exclusions)
        )
        b.clause(
            f"Exclusiones de la garantía de {coverage.title.lower()}",
            f"Además de las exclusiones generales, la garantía de {coverage.title.lower()} no cubre: {items}.",
            *(f"exclusion:{e.code}" for e in coverage.exclusions),
        )

    # Article 4: limits, deductibles and waiting periods.
    b.article("Límites, franquicias y carencias")
    for code, guarantee in product.guarantees.items():
        coverage = catalog.coverages[code]
        waiting = (
            f"con un periodo de carencia de {guarantee.waiting_days} días desde la fecha de efecto"
            if guarantee.waiting_days
            else "sin periodo de carencia"
        )
        deductible = (
            f"con una franquicia de {_eur(guarantee.deductible)}"
            if guarantee.deductible
            else "sin franquicia"
        )
        b.clause(
            coverage.title,
            f"""
La garantía de {coverage.title.lower()} se presta hasta un límite máximo
{_limit_text(guarantee)} por siniestro, {deductible} y {waiting}.
""",
            f"limits:{code}",
            f"waiting:{code}",
        )
    if product.guarantees:
        b.clause(
            "Cálculo de la indemnización",
            """
La indemnización se calcula sobre el importe de los daños debidamente acreditados y
relacionados con el siniestro, con el límite máximo de la garantía afectada. De la cantidad
resultante se descuenta la franquicia aplicable. Las partidas de una factura o presupuesto
que no guarden relación con el siniestro no son indemnizables.
""",
            "indemnity",
        )

    # Article 5: notice of claim.
    b.article("Comunicación del siniestro")
    b.clause(
        "Plazo de comunicación",
        """
El tomador o el asegurado deberán comunicar el siniestro a la Aseguradora en el plazo máximo
de siete días desde que lo conocieron, conforme al artículo 16 de la Ley de Contrato de
Seguro. Si la comunicación se produce fuera de plazo, la Aseguradora podrá reclamar los
daños y perjuicios causados por la falta de declaración, sin que el retraso suponga por sí
solo la pérdida del derecho a la indemnización.
""",
        "notice",
    )
    b.clause(
        "Deber de aminorar las consecuencias",
        """
El asegurado deberá emplear los medios a su alcance para aminorar las consecuencias del
siniestro, conforme al artículo 17 de la Ley de Contrato de Seguro. Los gastos razonables
en que incurra por este motivo serán a cargo de la Aseguradora.
""",
        "mitigation",
    )

    # Article 6: documentation.
    b.article("Documentación del siniestro")
    b.clause(
        "Documentación general",
        """
Junto con la comunicación del siniestro, el asegurado facilitará una descripción de las
circunstancias, la fecha y el lugar de ocurrencia, y cualquier documento que permita
valorar las consecuencias. La Aseguradora podrá solicitar la documentación adicional
razonablemente necesaria.
""",
        "documents:GENERAL",
    )
    for code in included:
        coverage = catalog.coverages[code]
        docs = "; ".join(catalog.documents[d].lower() for d in coverage.required_documents)
        b.clause(
            f"Documentación para {coverage.title.lower()}",
            f"""
Para tramitar un siniestro de {coverage.title.lower()} es imprescindible aportar: {docs}.
Hasta su recepción, la Aseguradora suspenderá la tramitación y lo comunicará al asegurado.
""",
            f"documents:{code}",
        )

    # Article 7: handling and payment.
    b.article("Tramitación y pago")
    b.clause(
        "Peritación",
        """
La Aseguradora podrá designar un perito para valorar los daños. Las partes podrán acordar la
indemnización a la vista de las facturas o presupuestos aportados.
""",
    )
    b.clause(
        "Pago de la indemnización",
        """
La Aseguradora pagará la indemnización dentro de los cuarenta días siguientes a la recepción
de la declaración del siniestro y de la documentación completa, conforme al artículo 18 de
la Ley de Contrato de Seguro, mediante transferencia a la cuenta designada por el asegurado.
""",
        "payment",
    )
    b.clause(
        "Verificación y fraude",
        f"""
La Aseguradora podrá verificar la veracidad de la declaración y de los documentos aportados.
Si el siniestro se hubiera declarado con mala fe, conforme al artículo 19 de la Ley de
Contrato de Seguro, la Aseguradora quedará liberada del pago. En ningún caso se rechazará un
siniestro por sospecha de fraude sin la revisión de un tramitador de {catalog.insurer.name}.
""",
        "fraud",
    )
    return b.conditions


def build_all_conditions(catalog: Catalog) -> dict[str, Conditions]:
    return {code: build_conditions(catalog, code) for code in catalog.products}


def render_markdown(catalog: Catalog, conditions: Conditions) -> str:
    product = catalog.product(conditions.product_code)
    lines = [
        f"# {catalog.insurer.name} · {product.name}",
        "",
        f"Condiciones generales del producto **{product.name}** (código `{conditions.product_code}`).",
        "",
        f"> {catalog.insurer.legal_notice}",
        "",
    ]
    current_article = ""
    for clause in conditions.clauses:
        if clause.article != current_article:
            current_article = clause.article
            lines += [f"## {clause.article}", ""]
        text = " ".join(clause.text.split())
        lines += [f"### {clause.clause_id} · {clause.title}", "", text, ""]
    return "\n".join(lines).rstrip() + "\n"
