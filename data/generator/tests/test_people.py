import random

from tramita_datagen.people import cif, iban, nif, plate


def test_nif_has_a_valid_check_letter() -> None:
    rng = random.Random(1)
    for _ in range(200):
        value = nif(rng)
        assert value[-1] == "TRWAGMYFPDXBNJZSQVHLCKE"[int(value[:-1]) % 23]


def test_iban_has_a_valid_checksum_and_the_unused_bank_code() -> None:
    rng = random.Random(2)
    for _ in range(200):
        compact = iban(rng).replace(" ", "")
        assert compact.startswith("ES") and compact[4:8] == "9999"
        rearranged = compact[4:] + compact[:4]
        numeric = "".join(str(int(c, 36)) for c in rearranged)
        assert int(numeric) % 97 == 1


def test_cif_has_a_valid_control_digit() -> None:
    rng = random.Random(3)
    for _ in range(200):
        value = cif(rng)
        digits = [int(c) for c in value[1:8]]
        even = sum(digits[1::2])
        odd = sum(sum(divmod(d * 2, 10)) for d in digits[0::2])
        assert int(value[8]) == (10 - (even + odd) % 10) % 10


def test_plates_follow_the_current_spanish_format() -> None:
    rng = random.Random(4)
    for _ in range(50):
        number, letters = plate(rng).split()
        assert len(number) == 4 and number.isdigit()
        assert len(letters) == 3 and not set(letters) & set("AEIOUQÑ")
