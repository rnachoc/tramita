package dev.tramita.core.catalog;

import dev.tramita.core.domain.CoverageCode;
import dev.tramita.core.domain.FraudSignalType;
import dev.tramita.core.domain.Line;
import dev.tramita.core.domain.RequiredDocument;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * The product catalog of the insurer, read from {@code data/policies/catalog.yaml}.
 *
 * <p>It is the same file the policy conditions are rendered from, so every limit, deductible and
 * waiting period the rules enforce is the one the policy text states.
 */
public record Catalog(
    Insurer insurer,
    Operations operations,
    Map<CoverageCode, Coverage> coverages,
    Map<RequiredDocument, String> documents,
    Map<String, Product> products) {

  public Optional<Product> product(String code) {
    return Optional.ofNullable(products.get(code));
  }

  public Coverage coverage(CoverageCode code) {
    return coverages.get(code);
  }

  public record Insurer(String name, String legalNotice) {}

  public record Operations(int reviewThresholdEur, int noticeDays, FraudRules fraud) {}

  public record FraudRules(
      double reviewThreshold,
      double investigationThreshold,
      Map<FraudSignalType, Double> weights,
      int earlyClaimDays,
      int frequentClaimsWindowDays,
      int frequentClaimsMin) {}

  public record Coverage(
      Line line,
      String title,
      String description,
      List<Exclusion> exclusions,
      List<RequiredDocument> requiredDocuments) {

    public boolean hasExclusion(String code) {
      return exclusions.stream().anyMatch(e -> e.code().equals(code));
    }
  }

  public record Exclusion(String code, String text) {}

  public record Product(String name, Line line, Map<CoverageCode, Guarantee> guarantees) {

    public Optional<Guarantee> guarantee(CoverageCode code) {
      return Optional.ofNullable(guarantees.get(code));
    }
  }

  public record Guarantee(Limit limit, int deductible, int waitingDays) {}

  /** A fixed amount, or the insured value of the vehicle stated in the policy. */
  public record Limit(BigDecimal amount, boolean insuredValue) {

    public static final String INSURED_VALUE = "insured_value";

    public static Limit parse(Object value) {
      if (INSURED_VALUE.equals(value)) {
        return new Limit(null, true);
      }
      return new Limit(new BigDecimal(value.toString()), false);
    }

    /** The limit for a policy, given its insured value. */
    public BigDecimal resolve(BigDecimal policyInsuredValue) {
      if (!insuredValue) {
        return amount;
      }
      if (policyInsuredValue == null) {
        throw new IllegalStateException("guarantee limited by insured value but policy has none");
      }
      return policyInsuredValue;
    }
  }
}
