from tramita_agents.documents.pii import Pseudonymizer, mask

COMPLAINT = (
    "Lucía Fernández García, con NIF 12345678Z, domicilio en Calle Mayor, 15, 3º B, Sevilla, "
    "teléfono +34 612 345 678 y correo lucia.fernandez@correo.example, cuenta "
    "ES46 9999 0000 1100 0000 0001. El vehículo con matrícula 1234 BCD fue forzado."
)
INVOICE = (
    "Fontanería Hermanos Robledo S.L. CIF B09318460. FACTURA Nº F2026-4661. Fecha: 25/01/2026. "
    "Cliente: Lucía Fernández García · NIF 12345678Z. TOTAL: 766,62 €"
)


def test_masks_every_kind_of_personal_data_in_a_police_report() -> None:
    masked = mask(COMPLAINT, Pseudonymizer())

    for value in (
        "Lucía Fernández",
        "12345678Z",
        "Calle Mayor, 15",
        "612 345 678",
        "lucia.fernandez@correo.example",
        "ES46 9999",
        "1234 BCD",
    ):
        assert value not in masked.text, value
    assert {
        "PERSON",
        "ES_NIF",
        "ADDRESS",
        "PHONE_NUMBER",
        "EMAIL_ADDRESS",
        "IBAN_CODE",
        "ES_PLATE",
    } <= set(masked.counts())


def test_keeps_what_the_rules_need() -> None:
    masked = mask(INVOICE, Pseudonymizer())

    for value in (
        "B09318460",
        "F2026-4661",
        "25/01/2026",
        "766,62 €",
        "Fontanería Hermanos Robledo S.L.",
    ):
        assert value in masked.text, value
    assert "12345678Z" not in masked.text


def test_the_same_person_gets_the_same_token_across_documents() -> None:
    pseudonyms = Pseudonymizer()

    first = mask(COMPLAINT, pseudonyms)
    second = mask(INVOICE, pseudonyms)

    assert "<ES_NIF_1>" in first.text
    assert "<ES_NIF_1>" in second.text
    assert "<ES_NIF_2>" not in second.text


def test_counts_expose_types_but_never_values() -> None:
    counts = mask(COMPLAINT, Pseudonymizer()).counts()

    assert all(isinstance(k, str) and isinstance(v, int) for k, v in counts.items())
    assert "12345678Z" not in repr(counts)


def test_email_validation_works_offline_and_with_reserved_test_domains() -> None:
    from tramita_agents.documents.pii import OfflineEmailRecognizer  # noqa: PLC0415

    recognizer = OfflineEmailRecognizer(supported_language="es")

    assert recognizer.validate_result("ana@correo.example")
    assert recognizer.validate_result("ana@gmail.com")
    assert not recognizer.validate_result("ana@not-a-tld.zzzzz")


def test_identifiers_misread_by_ocr_are_still_masked() -> None:
    # Wrong NIF letter and wrong IBAN check digits, as OCR errors produce.
    masked = mask("NIF 12345678A, cuenta ES00 9999 0000 1100 0000 0001.", Pseudonymizer())

    assert "12345678A" not in masked.text
    assert "9999 0000" not in masked.text


def test_addresses_include_floor_postal_code_and_city_even_when_misread() -> None:
    text = "Cliente: Rambla Lupe Méndez, 123, 4? D, 30171 Las Palmas de Gran Canaria. Total 10 €"

    masked = mask(text, Pseudonymizer())

    assert masked.text == "Cliente: <ADDRESS_1>. Total 10 €"


def test_names_next_to_labels_and_nifs_are_masked_even_when_ner_misses_them() -> None:
    text = (
        "Cliente\nOfelia Ferrero Uribe - NIF 71260208K\n"
        "Conductor Ana López Gil Pedro Ruiz Sanz\n"
        "Matrícula 10232 XFD 6170.DJ8\n"
    )

    masked = mask(text, Pseudonymizer())

    for value in ("Ofelia", "Ferrero", "Ana López", "Pedro Ruiz", "10232", "6170"):
        assert value not in masked.text, value


def test_ocr_damage_does_not_expose_identifiers() -> None:
    # Letter read as a comma, letter doubled, phone split over two lines.
    text = "NIF 33469590, y NIF 59890829WW. Teléfono +34 679\n037 894."

    masked = mask(text, Pseudonymizer())

    for value in ("33469590", "59890829", "679", "037 894"):
        assert value not in masked.text, value


def test_company_tax_ids_misread_as_numbers_are_kept() -> None:
    # OCR reads the "B" of a CIF as an "8": nine digits, shaped like a phone number.
    masked = mask("CIF 816618928 - Ronda de Asdrúbal, 83", Pseudonymizer())

    assert "CIF 816618928" in masked.text


def test_single_capitalised_words_and_insurers_are_not_people() -> None:
    text = "Suministro e instalación de placa. Aseguradora Cierzo (ficticia)."

    masked = mask(text, Pseudonymizer())

    assert masked.text == text
