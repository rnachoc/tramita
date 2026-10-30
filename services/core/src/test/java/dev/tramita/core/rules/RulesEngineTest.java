package dev.tramita.core.rules;

import static org.assertj.core.api.Assertions.assertThat;

import dev.tramita.core.TestCatalog;
import dev.tramita.core.domain.CoverageCode;
import dev.tramita.core.domain.Decision;
import dev.tramita.core.domain.DocumentType;
import dev.tramita.core.domain.FraudSignalType;
import dev.tramita.core.domain.Reason;
import dev.tramita.core.domain.RequiredDocument;
import dev.tramita.core.domain.Routing;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.EnumSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class RulesEngineTest {

  private static final LocalDate START = LocalDate.of(2026, 1, 1);
  private static final LocalDate INCIDENT = LocalDate.of(2026, 5, 10);

  private final RulesEngine engine = new RulesEngine(TestCatalog.CATALOG, TestCatalog.CLAUSES);

  // --- builders -----------------------------------------------------------------------------

  private static PolicyFacts policy(String product) {
    return new PolicyFacts("BR-" + product + "-000001", product, START, START.plusDays(364), null);
  }

  private static PolicyFacts vehiclePolicy(String product, String insuredValue) {
    return new PolicyFacts(
        "BR-" + product + "-000002",
        product,
        START,
        START.plusDays(364),
        new BigDecimal(insuredValue));
  }

  /**
   * An invoice whose two lines add up to {@code net} before 21% tax. The split has cents so the
   * lines never look like suspiciously round amounts.
   */
  private static RepairFacts invoice(String net) {
    BigDecimal total = new BigDecimal(net);
    BigDecimal first =
        total.multiply(new BigDecimal("0.6")).setScale(2).add(new BigDecimal("0.37"));
    return new RepairFacts(
        "B12345674",
        "F2026-0001",
        INCIDENT.plusDays(2),
        List.of(first, total.subtract(first)),
        BigDecimal.valueOf(21),
        total.multiply(new BigDecimal("1.21")).setScale(2));
  }

  private static ClaimFacts claim(CoverageCode type, Set<DocumentType> docs, RepairFacts repair) {
    return new ClaimFacts(
        "CL-1",
        type,
        INCIDENT,
        INCIDENT.plusDays(2),
        docs,
        List.of(INCIDENT.plusDays(2)),
        Optional.ofNullable(repair),
        List.of(),
        false);
  }

  private static ClaimFacts waterClaim(String net) {
    return claim(CoverageCode.HOME_WATER, EnumSet.of(DocumentType.INVOICE), invoice(net));
  }

  private static Proposal approve(String eligible, String... citations) {
    return new Proposal(
        Decision.APPROVE,
        eligible == null ? null : new BigDecimal(eligible),
        null,
        null,
        List.of(citations),
        List.of());
  }

  private static Proposal reject(String exclusion, String... citations) {
    return new Proposal(Decision.REJECT, null, null, exclusion, List.of(citations), List.of());
  }

  private static List<String> violationCodes(Evaluation e) {
    return e.violations().stream().map(Violation::code).toList();
  }

  // --- approvals ------------------------------------------------------------------------------

  @Test
  void approvesCoveredClaimAutomaticallyAndAppliesTheDeductible() {
    Evaluation e =
        engine.evaluate(policy("HP"), waterClaim("1000.00"), approve("1210.00", "HP-2.1"));

    assertThat(e.decision()).isEqualTo(Decision.APPROVE);
    assertThat(e.payableAmount()).isEqualByComparingTo("1110.00"); // 1210 - 100 deductible
    assertThat(e.routing()).isEqualTo(Routing.AUTO);
    assertThat(e.reasons()).contains(Reason.COVERED, Reason.DEDUCTIBLE_APPLIED);
    assertThat(e.violations()).isEmpty();
    assertThat(e.requiredCitations()).containsExactly("HP-2.1");
  }

  @Test
  void capsPaymentAtTheGuaranteeLimit() {
    ClaimFacts glass =
        claim(CoverageCode.HOME_GLASS, EnumSet.of(DocumentType.INVOICE), invoice("1500.00"));

    Evaluation e = engine.evaluate(policy("HP"), glass, approve("1815.00", "HP-2.3"));

    assertThat(e.payableAmount()).isEqualByComparingTo("1500.00");
    assertThat(e.reasons()).contains(Reason.LIMIT_APPLIED);
  }

  @Test
  void usesTheInsuredValueAsLimitForCollisionDamage() {
    ClaimFacts collision =
        claim(
            CoverageCode.AUTO_COLLISION,
            EnumSet.of(DocumentType.INVOICE, DocumentType.ACCIDENT_REPORT),
            invoice("10000.00"));

    Evaluation e =
        engine.evaluate(vehiclePolicy("AF", "9000"), collision, approve("12100.00", "AF-2.2"));

    assertThat(e.payableAmount()).isEqualByComparingTo("8700.00"); // 9000 limit - 300 deductible
    assertThat(e.reasons()).contains(Reason.LIMIT_APPLIED, Reason.ABOVE_REVIEW_THRESHOLD);
    assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
  }

  @Test
  void sendsLargePaymentsToAHuman() {
    Evaluation e =
        engine.evaluate(policy("HP"), waterClaim("4000.00"), approve("4840.00", "HP-2.1"));

    assertThat(e.payableAmount()).isEqualByComparingTo("4740.00");
    assertThat(e.reasons()).contains(Reason.ABOVE_REVIEW_THRESHOLD);
    assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
  }

  @Test
  void codeComputesTheAmountWhateverTheProposalSays() {
    Proposal proposal =
        new Proposal(
            Decision.APPROVE,
            new BigDecimal("1210.00"),
            new BigDecimal("9800.00"),
            null,
            List.of("HP-2.1"),
            List.of());

    Evaluation e = engine.evaluate(policy("HP"), waterClaim("1000.00"), proposal);

    assertThat(e.payableAmount()).isEqualByComparingTo("1110.00");
    assertThat(e.reasons()).contains(Reason.AMOUNT_RECALCULATED);
  }

  @Test
  void neverPaysMoreThanTheDocumentsSupport() {
    Evaluation e =
        engine.evaluate(policy("HP"), waterClaim("1000.00"), approve("5000.00", "HP-2.1"));

    assertThat(e.payableAmount()).isEqualByComparingTo("1110.00");
    assertThat(violationCodes(e)).contains("ELIGIBLE_ABOVE_DOCUMENTED");
    assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
  }

  @Test
  void flagsAdjustedAmountsForReviewWhenLinesAreExcluded() {
    Evaluation e =
        engine.evaluate(policy("HP"), waterClaim("1000.00"), approve("900.00", "HP-2.1"));

    assertThat(e.reasons()).contains(Reason.AMOUNT_ADJUSTED);
    assertThat(e.payableAmount()).isEqualByComparingTo("800.00");
    assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
  }

  @Test
  void flagsInvoicesWhoseTotalDoesNotAddUp() {
    RepairFacts inflated =
        new RepairFacts(
            "B12345674",
            "F1",
            INCIDENT,
            List.of(new BigDecimal("499.63"), new BigDecimal("500.37")),
            BigDecimal.valueOf(21),
            new BigDecimal("1500.00"));
    ClaimFacts claim = claim(CoverageCode.HOME_WATER, EnumSet.of(DocumentType.INVOICE), inflated);

    Evaluation e = engine.evaluate(policy("HP"), claim, approve("1210.00", "HP-2.1"));

    assertThat(e.reasons()).contains(Reason.AMOUNT_ADJUSTED);
    assertThat(e.payableAmount()).isEqualByComparingTo("1110.00");
  }

  @Test
  void lateNoticeNeedsReviewButKeepsTheCover() {
    ClaimFacts late =
        new ClaimFacts(
            "CL-1",
            CoverageCode.HOME_WATER,
            INCIDENT,
            INCIDENT.plusDays(20),
            EnumSet.of(DocumentType.INVOICE),
            List.of(INCIDENT.plusDays(1)),
            Optional.of(invoice("1000.00")),
            List.of(),
            false);

    Evaluation e = engine.evaluate(policy("HP"), late, approve("1210.00", "HP-2.1"));

    assertThat(e.decision()).isEqualTo(Decision.APPROVE);
    assertThat(e.reasons()).contains(Reason.LATE_NOTICE);
    assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
  }

  // --- rules that override the proposal ----------------------------------------------------------

  @Nested
  class Overrides {

    @Test
    void rejectsGuaranteesTheProductDoesNotInclude() {
      ClaimFacts glass =
          claim(CoverageCode.HOME_GLASS, EnumSet.of(DocumentType.INVOICE), invoice("300.00"));

      Evaluation e = engine.evaluate(policy("HB"), glass, approve("363.00", "HB-2.1"));

      assertThat(e.decision()).isEqualTo(Decision.REJECT);
      assertThat(e.reasons()).contains(Reason.NOT_INCLUDED);
      assertThat(violationCodes(e)).contains("DECISION_OVERRIDDEN");
      assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
      assertThat(e.payableAmount()).isZero();
      assertThat(e.requiredCitations()).hasSize(1);
    }

    @Test
    void rejectsIncidentsWithinTheWaitingPeriod() {
      ClaimFacts theft =
          new ClaimFacts(
              "CL-1",
              CoverageCode.HOME_THEFT,
              START.plusDays(10),
              START.plusDays(11),
              EnumSet.of(DocumentType.INVOICE, DocumentType.POLICE_REPORT),
              List.of(START.plusDays(11)),
              Optional.of(invoice("800.00")),
              List.of(),
              false);
      String waiting = TestCatalog.CLAUSES.clauseFor("HB", "waiting:HOME_THEFT").orElseThrow();

      Evaluation e = engine.evaluate(policy("HB"), theft, reject(null, waiting));

      assertThat(e.decision()).isEqualTo(Decision.REJECT);
      assertThat(e.reasons()).contains(Reason.WAITING_PERIOD);
      assertThat(e.violations()).isEmpty();
      assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
    }

    @Test
    void rejectsIncidentsOutsideThePolicyPeriod() {
      ClaimFacts before =
          new ClaimFacts(
              "CL-1",
              CoverageCode.HOME_WATER,
              START.minusDays(3),
              START.plusDays(1),
              EnumSet.of(DocumentType.INVOICE),
              List.of(),
              Optional.of(invoice("500.00")),
              List.of(),
              false);

      Evaluation e = engine.evaluate(policy("HP"), before, approve("605.00", "HP-2.1"));

      assertThat(e.decision()).isEqualTo(Decision.REJECT);
      assertThat(e.reasons()).contains(Reason.POLICY_NOT_IN_FORCE);
    }

    @Test
    void asksForMissingDocumentsInsteadOfApproving() {
      ClaimFacts theft =
          claim(CoverageCode.HOME_THEFT, EnumSet.of(DocumentType.INVOICE), invoice("800.00"));

      Evaluation e = engine.evaluate(policy("HP"), theft, approve("968.00", "HP-2.2"));

      assertThat(e.decision()).isEqualTo(Decision.REQUEST_INFO);
      assertThat(e.missingDocuments()).containsExactly(RequiredDocument.POLICE_REPORT);
      assertThat(violationCodes(e)).contains("APPROVAL_WITH_MISSING_DOCUMENTS");
      // Asking for documents is low risk, so it happens without a human.
      assertThat(e.routing()).isEqualTo(Routing.AUTO);
    }

    @Test
    void requestsForInformationTheCatalogDoesNotRequireNeedAHuman() {
      Proposal askForMore =
          new Proposal(Decision.REQUEST_INFO, null, null, null, List.of("HP-1.1"), List.of());

      Evaluation e = engine.evaluate(policy("HP"), waterClaim("1000.00"), askForMore);

      assertThat(e.decision()).isEqualTo(Decision.REQUEST_INFO);
      assertThat(e.reasons()).contains(Reason.ADDITIONAL_INFORMATION);
      assertThat(e.missingDocuments()).isEmpty();
      assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
    }

    @Test
    void approvalWithoutExtractedAmountsAsksForThemThroughAHuman() {
      ClaimFacts noAmounts = claim(CoverageCode.HOME_WATER, EnumSet.of(DocumentType.INVOICE), null);

      Evaluation e = engine.evaluate(policy("HP"), noAmounts, approve("1210.00", "HP-2.1"));

      assertThat(e.decision()).isEqualTo(Decision.REQUEST_INFO);
      assertThat(violationCodes(e)).contains("NO_AMOUNTS");
      assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
    }
  }

  // --- exclusions -------------------------------------------------------------------------------

  @Nested
  class Exclusions {

    @Test
    void acceptsRejectionsGroundedOnACatalogExclusion() {
      String clause =
          TestCatalog.CLAUSES.clauseFor("HP", "exclusion:WATER_MAINTENANCE").orElseThrow();

      Evaluation e =
          engine.evaluate(policy("HP"), waterClaim("700.00"), reject("WATER_MAINTENANCE", clause));

      assertThat(e.decision()).isEqualTo(Decision.REJECT);
      assertThat(e.reasons()).contains(Reason.EXCLUSION);
      assertThat(e.violations()).isEmpty();
      assertThat(e.requiredCitations()).containsExactly(clause);
      assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
    }

    @Test
    void flagsRejectionsWithoutAValidExclusion() {
      Evaluation e =
          engine.evaluate(policy("HP"), waterClaim("700.00"), reject("AUTO_ALCOHOL", "HP-3.2"));

      assertThat(violationCodes(e)).contains("UNGROUNDED_REJECTION");
      assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
    }
  }

  // --- citations
  // ----------------------------------------------------------------------------------

  @Nested
  class Citations {

    @Test
    void rejectsCitationsFromAnotherProductOrThatDoNotExist() {
      Evaluation e =
          engine.evaluate(
              policy("HP"),
              waterClaim("1000.00"),
              approve("1210.00", "HP-2.1", "AF-2.2", "HP-99.9"));

      assertThat(violationCodes(e)).containsOnly("INVALID_CITATION");
      assertThat(e.violations()).hasSize(2);
      assertThat(e.routing()).isEqualTo(Routing.HUMAN_REVIEW);
    }

    @Test
    void requiresCitingTheClauseThatGroundsTheDecision() {
      Evaluation e = engine.evaluate(policy("HP"), waterClaim("1000.00"), approve("1210.00"));

      assertThat(violationCodes(e)).containsExactly("MISSING_CITATION");
    }
  }

  // --- fraud
  // ----------------------------------------------------------------------------------------

  @Nested
  class Fraud {

    @Test
    void duplicateInvoiceSendsTheClaimToInvestigation() {
      ClaimFacts duplicate =
          new ClaimFacts(
              "CL-2",
              CoverageCode.HOME_WATER,
              INCIDENT,
              INCIDENT.plusDays(1),
              EnumSet.of(DocumentType.INVOICE),
              List.of(INCIDENT.plusDays(1)),
              Optional.of(invoice("1000.00")),
              List.of(),
              true);

      Evaluation e = engine.evaluate(policy("HP"), duplicate, approve("1210.00", "HP-2.1"));

      assertThat(e.fraudScore()).isEqualTo(0.8);
      assertThat(e.routing()).isEqualTo(Routing.FRAUD_INVESTIGATION);
      assertThat(e.reasons()).contains(Reason.FRAUD_SUSPECTED);
      // The decision on the merits is kept for the investigator; nothing is rejected automatically.
      assertThat(e.decision()).isEqualTo(Decision.APPROVE);
    }

    @Test
    void combinesModelAndRuleSignals() {
      ClaimFacts backdated =
          new ClaimFacts(
              "CL-3",
              CoverageCode.HOME_WATER,
              INCIDENT,
              INCIDENT.plusDays(1),
              EnumSet.of(DocumentType.INVOICE),
              List.of(INCIDENT.minusDays(5)),
              Optional.of(invoice("1000.00")),
              List.of(),
              false);
      Proposal proposal =
          new Proposal(
              Decision.APPROVE,
              new BigDecimal("1210.00"),
              null,
              null,
              List.of("HP-2.1"),
              List.of(
                  new FraudSignal(
                      FraudSignalType.DESCRIPTION_MISMATCH,
                      "Invoice repairs a roof; the claim describes a kitchen pipe",
                      1.0,
                      SignalSource.MODEL)));

      Evaluation e = engine.evaluate(policy("HP"), backdated, proposal);

      assertThat(e.fraudSignals())
          .extracting(FraudSignal::type)
          .containsExactlyInAnyOrder(
              FraudSignalType.DATE_INCONSISTENCY, FraudSignalType.DESCRIPTION_MISMATCH);
      assertThat(e.fraudScore()).isEqualTo(0.75);
      assertThat(e.routing()).isEqualTo(Routing.FRAUD_INVESTIGATION);
    }

    @Test
    void discardsModelSignalsWithoutEvidence() {
      Proposal proposal =
          new Proposal(
              Decision.APPROVE,
              new BigDecimal("1210.00"),
              null,
              null,
              List.of("HP-2.1"),
              List.of(
                  new FraudSignal(
                      FraudSignalType.DESCRIPTION_MISMATCH, " ", 0.9, SignalSource.MODEL)));

      Evaluation e = engine.evaluate(policy("HP"), waterClaim("1000.00"), proposal);

      assertThat(e.fraudSignals()).isEmpty();
      assertThat(violationCodes(e)).contains("SIGNAL_DISCARDED");
    }

    @Test
    void aSingleWeakSignalDoesNotChangeTheRouting() {
      ClaimFacts early =
          new ClaimFacts(
              "CL-4",
              CoverageCode.HOME_WATER,
              START.plusDays(20),
              START.plusDays(21),
              EnumSet.of(DocumentType.INVOICE),
              List.of(START.plusDays(21)),
              Optional.of(invoice("1000.00")),
              List.of(),
              false);

      Evaluation e = engine.evaluate(policy("HP"), early, approve("1210.00", "HP-2.1"));

      assertThat(e.fraudSignals())
          .extracting(FraudSignal::type)
          .containsExactly(FraudSignalType.EARLY_CLAIM);
      assertThat(e.routing()).isEqualTo(Routing.AUTO);
    }
  }
}
