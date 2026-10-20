package dev.tramita.core.rules;

import java.math.BigDecimal;
import java.time.LocalDate;

/** What the rules need to know about the policy a claim is filed under. */
public record PolicyFacts(
    String policyNumber,
    String productCode,
    LocalDate startDate,
    LocalDate endDate,
    BigDecimal insuredValue) {

  public boolean inForceOn(LocalDate day) {
    return !day.isBefore(startDate) && !day.isAfter(endDate);
  }
}
