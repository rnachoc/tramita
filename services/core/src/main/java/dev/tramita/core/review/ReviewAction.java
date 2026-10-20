package dev.tramita.core.review;

/** What a claims handler does with a proposal. */
public enum ReviewAction {
  /** Accept the rules-checked proposal as it is. */
  APPROVE,
  /** Accept with a different decision or amount; the correction becomes an eval case. */
  CORRECT,
  /** Reject the claim. */
  REJECT
}
