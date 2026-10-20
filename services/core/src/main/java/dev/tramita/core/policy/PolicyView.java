package dev.tramita.core.policy;

import dev.tramita.core.domain.Line;
import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * A policy as exposed by the API. Personal data of the holder is reduced to an id and a city, so
 * views can be shown to analysts and passed to agents without leaking identity documents.
 */
public record PolicyView(
    String policyNumber,
    String productCode,
    String productName,
    Line line,
    LocalDate startDate,
    LocalDate endDate,
    BigDecimal insuredValue,
    String vehiclePlate,
    String holderId,
    String holderCity) {

  public static PolicyView of(Policy p, String productName) {
    return new PolicyView(
        p.getPolicyNumber(),
        p.getProductCode(),
        productName,
        p.getLine(),
        p.getStartDate(),
        p.getEndDate(),
        p.getInsuredValue(),
        p.getVehiclePlate(),
        p.getHolder().getHolderId(),
        p.getHolder().getCity());
  }
}
