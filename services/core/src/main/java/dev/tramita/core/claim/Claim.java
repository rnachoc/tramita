package dev.tramita.core.claim;

import dev.tramita.core.domain.ClaimStatus;
import dev.tramita.core.domain.CoverageCode;
import dev.tramita.core.policy.Policy;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

/** A claim as filed by the policyholder, and its current status. */
@Entity
@Table(name = "claims")
public class Claim {

  @Id private String claimId;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "policy_number")
  private Policy policy;

  @Enumerated(EnumType.STRING)
  private CoverageCode claimType;

  private LocalDate incidentDate;
  private LocalDate reportedDate;
  private String location;
  private String description;
  private BigDecimal claimedAmount;
  private String contactPhone;
  private String contactEmail;

  @Enumerated(EnumType.STRING)
  private ClaimStatus status;

  private Instant createdAt;
  private Instant updatedAt;

  @Version private long version;

  protected Claim() {}

  public Claim(
      String claimId,
      Policy policy,
      CoverageCode claimType,
      LocalDate incidentDate,
      LocalDate reportedDate,
      String location,
      String description,
      BigDecimal claimedAmount,
      String contactPhone,
      String contactEmail,
      Instant now) {
    this.claimId = claimId;
    this.policy = policy;
    this.claimType = claimType;
    this.incidentDate = incidentDate;
    this.reportedDate = reportedDate;
    this.location = location;
    this.description = description;
    this.claimedAmount = claimedAmount;
    this.contactPhone = contactPhone;
    this.contactEmail = contactEmail;
    this.status = ClaimStatus.RECEIVED;
    this.createdAt = now;
    this.updatedAt = now;
  }

  /** Moves the claim to a new status. Paid and rejected claims are final. */
  public void moveTo(ClaimStatus next, Instant now) {
    if (status == ClaimStatus.PAID || status == ClaimStatus.REJECTED) {
      throw new IllegalStateException("claim " + claimId + " is closed (" + status + ")");
    }
    this.status = next;
    this.updatedAt = now;
  }

  public String getClaimId() {
    return claimId;
  }

  public Policy getPolicy() {
    return policy;
  }

  public CoverageCode getClaimType() {
    return claimType;
  }

  public LocalDate getIncidentDate() {
    return incidentDate;
  }

  public LocalDate getReportedDate() {
    return reportedDate;
  }

  public String getLocation() {
    return location;
  }

  public String getDescription() {
    return description;
  }

  public BigDecimal getClaimedAmount() {
    return claimedAmount;
  }

  public String getContactPhone() {
    return contactPhone;
  }

  public String getContactEmail() {
    return contactEmail;
  }

  public ClaimStatus getStatus() {
    return status;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
