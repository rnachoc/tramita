# ADR 0011: Documents are read from masked inputs, and code decides what a reading is worth

- Status: accepted
- Date: 2026-11-02

## Context

Claims arrive with invoices, estimates, police reports and accident reports, as born-digital PDFs
or as scans. The agents need their facts (dates, supplier tax id, document number, amounts,
lines), but the documents are full of personal data (names, NIF/NIE, addresses, phones, plates,
IBANs) that must not reach a model, a trace or a log. Scans are noisy, and some documents carry
text written to steer an automated reader.

## Options considered

**Privacy.**

1. Send documents as they are and rely on the provider's data terms. Simple, but personal data
   leaves the system on every call and ends up in traces.
2. Extract text locally (PDF text layer, OCR) and send only masked text. Safe, but on scans the
   model would read OCR errors instead of the page.
3. Option 2 for PDFs; for scans, use OCR only to find personal data, black it out in the image,
   and send the redacted image with the masked OCR text.

**Confidence.** Ask the model how sure it is, or compute it in code from evidence.

**Injection.** Rely on the prompt, or add independent layers.

## Decision

- **Masking (option 3).** Presidio with the Spanish spaCy model and Spain-specific recognisers
  (NIF, NIE, IBAN, phones, e-mail, plates, street addresses with floor, postal code and city),
  plus fallbacks for what OCR damages: identifiers whose checksum fails, names and NIFs found by
  the labels the documents print, phones split over two lines. Each value becomes a stable token
  per claim (`<PERSON_1>`), so the model can relate mentions without seeing values. Company tax
  ids, amounts, dates and document numbers are kept: the rules need them.
- **Scans.** Tesseract (Spanish) runs on the image upscaled to about 300 dpi, its words are laid
  out in visual rows (tables are read column by column otherwise), personal data is found in that
  text and every overlapping word box is painted black. The original never leaves the store.
- **Structured output.** The model fills a strict schema (`documents/schemas.py`); amounts and
  dates travel as strings and are parsed in code.
- **Confidence from evidence.** Code checks formats (CIF control digit), arithmetic (lines,
  tax, total) and looks each value up in a second reading: the scan's OCR, or the PDF text layer.
  Key fields below 0.6 go to review, and the typed facts the rules act on are only sent to the
  core when they reach that threshold (amounts only as a complete set). An inflated total is
  reported as a failed check but kept as printed, because the rules act on it.
- **Injection, in depth.** The document is quoted in tags it cannot close and the system prompt
  treats it as data; the model reports embedded instructions in a dedicated field; a deterministic
  detector flags them too; the output schema has no field that could approve or pay; and the
  decision belongs to the rules engine (ADR 0008).

## Consequences

- Measured on the generated data with the rule-based baseline (ADR 0010): no personal value of
  the ground truth reaches what the model receives, the redacted scans as OCR reads them again,
  or what the core receives; no rule value is lost to masking; no wrong typed fact is sent to
  the rules. CI keeps these at zero with a regression gate.
- OCR does not see very small print. Personal data printed that small would not be blacked out,
  and instructions hidden that way in scans are left to the vision model: the detector finds the
  ones planted in PDFs but none of those in scans.
- Masking removes context the model might use (a customer's name matching the policyholder's).
  Those comparisons belong in code against the core's records, not in the model.
- Tesseract becomes a runtime dependency of the agent service (and of CI).
