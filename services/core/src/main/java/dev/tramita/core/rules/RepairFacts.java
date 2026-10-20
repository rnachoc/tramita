package dev.tramita.core.rules;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.List;

/**
 * Amounts extracted from the invoice or estimate the claim is valued on.
 *
 * @param lineAmounts amount of every line, before tax
 * @param taxRatePercent tax rate applied to the lines, for example 21
 * @param statedTotal the total printed on the document, which may not add up
 */
public record RepairFacts(
    String issuerTaxId,
    String number,
    LocalDate issueDate,
    List<BigDecimal> lineAmounts,
    BigDecimal taxRatePercent,
    BigDecimal statedTotal) {

  private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

  /** Sum of the lines plus tax: the amount the document actually supports. */
  public BigDecimal computedTotal() {
    BigDecimal subtotal = lineAmounts.stream().reduce(BigDecimal.ZERO, BigDecimal::add);
    BigDecimal factor = BigDecimal.ONE.add(taxRatePercent.divide(HUNDRED));
    return subtotal.multiply(factor).setScale(2, RoundingMode.HALF_UP);
  }
}
