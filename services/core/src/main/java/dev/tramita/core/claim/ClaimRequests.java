package dev.tramita.core.claim;

import dev.tramita.core.domain.CoverageCode;
import dev.tramita.core.domain.DocumentType;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/** Request bodies for registering claims, documents and extractions. */
public final class ClaimRequests {

  private ClaimRequests() {}

  /** The claim form, as submitted by the policyholder. */
  public record Register(
      @NotBlank @Size(max = 24) String claimId,
      @NotBlank String policyNumber,
      @NotNull LocalDate reportedDate,
      @NotNull LocalDate incidentDate,
      @NotNull CoverageCode claimType,
      @NotBlank String location,
      @NotBlank @Size(max = 10_000) String description,
      @DecimalMin("0.00") BigDecimal claimedAmount,
      String contactPhone,
      String contactEmail) {}

  /** A document received with the claim; the file itself is in the object store. */
  public record AddDocument(
      @NotBlank @Size(max = 24) String documentId,
      @NotNull DocumentType documentType,
      @NotBlank String filename,
      String storageKey) {}

  /**
   * Facts read from a document by the agent service. {@code fields} holds the full structured
   * extraction with personal data already masked; the typed fields are what the rules use.
   */
  public record Extraction(
      @NotNull Map<String, Object> fields,
      LocalDate issueDate,
      String issuerTaxId,
      String documentNumber,
      BigDecimal statedTotal,
      BigDecimal taxRate,
      List<BigDecimal> lineAmounts) {}
}
