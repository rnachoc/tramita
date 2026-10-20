import pytest

from tramita_datagen.catalog import Catalog, load_catalog
from tramita_datagen.models import Dataset
from tramita_datagen.policies import Conditions, build_all_conditions


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return load_catalog()


@pytest.fixture(scope="session")
def conditions(catalog: Catalog) -> dict[str, Conditions]:
    return build_all_conditions(catalog)


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    from tramita_datagen.cli import generate  # noqa: PLC0415 - keeps fixtures importable per module

    return generate()
