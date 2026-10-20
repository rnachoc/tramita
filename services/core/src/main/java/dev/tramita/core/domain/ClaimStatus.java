package dev.tramita.core.domain;

/** Lifecycle of a claim in the system of record. */
public enum ClaimStatus {
  RECEIVED,
  WAITING_DOCUMENTS,
  PENDING_REVIEW,
  UNDER_INVESTIGATION,
  APPROVED,
  REJECTED,
  PAID;

  /** Whether a human decision can still be recorded for a claim in this status. */
  public boolean awaitsHuman() {
    return this == PENDING_REVIEW || this == UNDER_INVESTIGATION;
  }
}
