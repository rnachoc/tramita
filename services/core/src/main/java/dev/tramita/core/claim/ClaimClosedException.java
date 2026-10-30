package dev.tramita.core.claim;

import dev.tramita.core.domain.ClaimStatus;

/** A change was attempted on a claim that is paid or rejected. */
public class ClaimClosedException extends RuntimeException {

  public ClaimClosedException(String claimId, ClaimStatus status) {
    super("Claim " + claimId + " is closed (" + status + ") and cannot change any more");
  }
}
