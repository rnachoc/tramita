package dev.tramita.core.claim;

import dev.tramita.core.domain.DocumentType;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * A document attached to a claim. The original file lives in the object store; this row keeps its
 * metadata and the facts extracted from it, with personal data already masked by the agent service.
 */
@Entity
@Table(name = "claim_documents")
public class ClaimDocument {

  @Id private String documentId;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "claim_id")
  private Claim claim;

  @Enumerated(EnumType.STRING)
  private DocumentType documentType;

  private String filename;
  private String storageKey;
  private Instant receivedAt;

  @JdbcTypeCode(SqlTypes.JSON)
  private Map<String, Object> extraction;

  private Instant extractedAt;
  private LocalDate issueDate;
  private String issuerTaxId;
  private String documentNumber;
  private BigDecimal statedTotal;
  private BigDecimal taxRate;

  @JdbcTypeCode(SqlTypes.JSON)
  private List<BigDecimal> lineAmounts;

  protected ClaimDocument() {}

  public ClaimDocument(
      String documentId,
      Claim claim,
      DocumentType documentType,
      String filename,
      String storageKey,
      Instant receivedAt) {
    this.documentId = documentId;
    this.claim = claim;
    this.documentType = documentType;
    this.filename = filename;
    this.storageKey = storageKey;
    this.receivedAt = receivedAt;
  }

  /** Records what was read from the document. Re-extraction replaces the previous result. */
  public void recordExtraction(
      Map<String, Object> extraction,
      LocalDate issueDate,
      String issuerTaxId,
      String documentNumber,
      BigDecimal statedTotal,
      BigDecimal taxRate,
      List<BigDecimal> lineAmounts,
      Instant now) {
    this.extraction = extraction;
    this.issueDate = issueDate;
    this.issuerTaxId = issuerTaxId;
    this.documentNumber = documentNumber;
    this.statedTotal = statedTotal;
    this.taxRate = taxRate;
    this.lineAmounts = lineAmounts == null ? null : List.copyOf(lineAmounts);
    this.extractedAt = now;
  }

  public boolean hasAmounts() {
    return lineAmounts != null && !lineAmounts.isEmpty() && statedTotal != null && taxRate != null;
  }

  public String getDocumentId() {
    return documentId;
  }

  public Claim getClaim() {
    return claim;
  }

  public DocumentType getDocumentType() {
    return documentType;
  }

  public String getFilename() {
    return filename;
  }

  public String getStorageKey() {
    return storageKey;
  }

  public Instant getReceivedAt() {
    return receivedAt;
  }

  public Map<String, Object> getExtraction() {
    return extraction;
  }

  public Instant getExtractedAt() {
    return extractedAt;
  }

  public LocalDate getIssueDate() {
    return issueDate;
  }

  public String getIssuerTaxId() {
    return issuerTaxId;
  }

  public String getDocumentNumber() {
    return documentNumber;
  }

  public BigDecimal getStatedTotal() {
    return statedTotal;
  }

  public BigDecimal getTaxRate() {
    return taxRate;
  }

  public List<BigDecimal> getLineAmounts() {
    return lineAmounts;
  }
}
