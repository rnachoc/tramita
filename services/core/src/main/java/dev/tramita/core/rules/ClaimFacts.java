package dev.tramita.core.rules;

import dev.tramita.core.domain.CoverageCode;
import dev.tramita.core.domain.DocumentType;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * What the rules know about a claim, from the claim form, the extracted documents and the insurer's
 * own records.
 *
 * @param documentTypes types of the documents received
 * @param documentDates issue or filing date of every received document
 * @param amounts the invoice (or, failing that, the estimate) the claim is valued on
 * @param earlierIncidents incident dates of claims on the same policy reported before this one
 * @param repairDocumentSeenBefore whether an earlier claim already used the same invoice
 */
public record ClaimFacts(
    String claimId,
    CoverageCode claimType,
    LocalDate incidentDate,
    LocalDate reportedDate,
    Set<DocumentType> documentTypes,
    List<LocalDate> documentDates,
    Optional<RepairFacts> amounts,
    List<LocalDate> earlierIncidents,
    boolean repairDocumentSeenBefore) {}
