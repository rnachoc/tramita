package dev.tramita.core.payment;

import dev.tramita.core.claim.Claim;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** A payment of an indemnity. The database allows at most one per claim. */
@Entity
@Table(name = "payments")
public class Payment {

  /** What authorised the payment. */
  public enum Trigger {
    RULES,
    REVIEW
  }

  @Id private UUID paymentId;

  @OneToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "claim_id")
  private Claim claim;

  private String idempotencyKey;
  private BigDecimal amount;
  private String ibanMasked;
  private String reference;

  @Enumerated(EnumType.STRING)
  private Trigger triggeredBy;

  private Instant executedAt;

  protected Payment() {}

  public Payment(
      Claim claim,
      String idempotencyKey,
      BigDecimal amount,
      String ibanMasked,
      Trigger triggeredBy,
      Instant executedAt) {
    this.paymentId = UUID.randomUUID();
    this.claim = claim;
    this.idempotencyKey = idempotencyKey;
    this.amount = amount;
    this.ibanMasked = ibanMasked;
    this.reference = "PAY-" + claim.getClaimId();
    this.triggeredBy = triggeredBy;
    this.executedAt = executedAt;
  }

  public UUID getPaymentId() {
    return paymentId;
  }

  public Claim getClaim() {
    return claim;
  }

  public String getIdempotencyKey() {
    return idempotencyKey;
  }

  public BigDecimal getAmount() {
    return amount;
  }

  public String getIbanMasked() {
    return ibanMasked;
  }

  public String getReference() {
    return reference;
  }

  public Trigger getTriggeredBy() {
    return triggeredBy;
  }

  public Instant getExecutedAt() {
    return executedAt;
  }
}
