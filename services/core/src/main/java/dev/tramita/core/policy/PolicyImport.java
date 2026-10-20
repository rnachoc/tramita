package dev.tramita.core.policy;

import dev.tramita.core.domain.Line;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/**
 * Reference data import, in the same shape the data generator writes ({@code policyholders.json}
 * and {@code policies.json}).
 */
public final class PolicyImport {

  private PolicyImport() {}

  public record Request(
      @NotNull @Valid List<Holder> policyholders, @NotNull @Valid List<PolicyItem> policies) {}

  public record Address(
      @NotBlank String street,
      @NotBlank String postalCode,
      @NotBlank String city,
      @NotBlank String province) {}

  public record Holder(
      @NotBlank String holderId,
      @NotBlank String fullName,
      @NotBlank String nif,
      @NotNull LocalDate birthDate,
      @NotBlank String email,
      @NotBlank String phone,
      @NotNull @Valid Address address,
      @NotBlank String iban) {}

  public record Vehicle(@NotBlank String plate, String make, String model, Integer year) {}

  public record PolicyItem(
      @NotBlank String policyNumber,
      @NotBlank String holderId,
      @NotBlank String productCode,
      @NotNull Line line,
      @NotNull LocalDate startDate,
      @NotNull LocalDate endDate,
      @NotNull BigDecimal annualPremium,
      @Valid Address insuredAddress,
      @Valid Vehicle vehicle,
      BigDecimal insuredValue) {}

  public record Result(int policyholders, int policies) {}
}
