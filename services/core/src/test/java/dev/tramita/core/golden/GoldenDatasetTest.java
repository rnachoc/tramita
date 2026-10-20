package dev.tramita.core.golden;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.tramita.core.TestCatalog;
import dev.tramita.core.domain.CoverageCode;
import dev.tramita.core.domain.Decision;
import dev.tramita.core.domain.DocumentType;
import dev.tramita.core.domain.FraudSignalType;
import dev.tramita.core.domain.Routing;
import dev.tramita.core.rules.ClaimFacts;
import dev.tramita.core.rules.Evaluation;
import dev.tramita.core.rules.FraudSignal;
import dev.tramita.core.rules.PolicyFacts;
import dev.tramita.core.rules.Proposal;
import dev.tramita.core.rules.RepairFacts;
import dev.tramita.core.rules.RulesEngine;
import dev.tramita.core.rules.SignalSource;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * Cross-checks the Java rules engine against the Python reference resolver of the data generator on
 * every claim of the synthetic dataset.
 *
 * <p>The two implementations are written independently. Given the true document facts and a correct
 * proposal, they must agree on decision, routing, payable amount and fraud score. Run {@code make
 * data} first; the dataset is not committed.
 */
class GoldenDatasetTest {

  private static final Path DATASET = Path.of("..", "..", "data", "generated");
  private static final ObjectMapper JSON = new ObjectMapper();

  private static Map<String, JsonNode> policies;
  private static Map<String, JsonNode> claims;
  private static Map<String, List<JsonNode>> documentsByClaim;
  private static List<JsonNode> expected;

  private final RulesEngine engine = new RulesEngine(TestCatalog.CATALOG, TestCatalog.CLAUSES);

  @BeforeAll
  static void loadDataset() throws IOException {
    assertThat(DATASET.resolve("expected.json"))
        .as("Synthetic dataset missing: run `make data` from the repository root")
        .exists();
    policies = index(read("policies.json"), "policy_number");
    claims = index(read("claims.json"), "claim_id");
    documentsByClaim = new HashMap<>();
    for (JsonNode doc : read("documents.json")) {
      documentsByClaim
          .computeIfAbsent(doc.get("claim_id").asText(), k -> new ArrayList<>())
          .add(doc);
    }
    expected = read("expected.json");
  }

  @Test
  void rulesEngineAgreesWithTheReferenceResolverOnEveryClaim() {
    List<String> disagreements = new ArrayList<>();
    Map<String, List<LocalDate>> incidentsByPolicy = new HashMap<>();
    Set<String> seenDocuments = new java.util.HashSet<>();

    for (JsonNode exp : expected) { // expected.json is in reporting order
      String claimId = exp.get("claim_id").asText();
      JsonNode claim = claims.get(claimId);
      JsonNode policy = policies.get(claim.get("policy_number").asText());
      List<JsonNode> docs = documentsByClaim.getOrDefault(claimId, List.of());

      List<String> keys = new ArrayList<>();
      for (JsonNode d : docs) {
        if (d.hasNonNull("repair")) {
          JsonNode r = d.get("repair");
          keys.add(r.at("/issuer/tax_id").asText() + "|" + r.get("number").asText());
        }
      }
      boolean seenBefore = keys.stream().anyMatch(seenDocuments::contains);
      seenDocuments.addAll(keys);
      List<LocalDate> earlier =
          incidentsByPolicy.computeIfAbsent(
              claim.get("policy_number").asText(), k -> new ArrayList<>());

      Evaluation e =
          engine.evaluate(
              policyFacts(policy),
              claimFacts(claim, docs, List.copyOf(earlier), seenBefore),
              proposal(exp));
      earlier.add(LocalDate.parse(claim.get("incident_date").asText()));

      compare(claimId, exp, e, disagreements);
    }
    assertThat(disagreements).as("claims where Java and Python disagree").isEmpty();
    assertThat(expected).hasSize(150);
  }

  private static void compare(String claimId, JsonNode exp, Evaluation e, List<String> out) {
    Decision decision = Decision.valueOf(exp.get("decision").asText());
    Routing routing = Routing.valueOf(exp.get("routing").asText());
    BigDecimal payable = new BigDecimal(exp.get("payable_amount").asText());
    double score = exp.get("fraud_score").asDouble();
    if (e.decision() != decision
        || e.routing() != routing
        || e.payableAmount().compareTo(payable) != 0
        || Math.abs(e.fraudScore() - score) > 1e-4
        || !e.violations().isEmpty()) {
      out.add(
          "%s expected %s/%s/%s/%.4f got %s/%s/%s/%.4f violations=%s"
              .formatted(
                  claimId,
                  decision,
                  routing,
                  payable,
                  score,
                  e.decision(),
                  e.routing(),
                  e.payableAmount(),
                  e.fraudScore(),
                  e.violations()));
    }
  }

  // --- building rules inputs from the generated facts
  // ----------------------------------------------

  private static PolicyFacts policyFacts(JsonNode p) {
    BigDecimal insured =
        p.hasNonNull("insured_value") ? new BigDecimal(p.get("insured_value").asText()) : null;
    return new PolicyFacts(
        p.get("policy_number").asText(),
        p.get("product_code").asText(),
        LocalDate.parse(p.get("start_date").asText()),
        LocalDate.parse(p.get("end_date").asText()),
        insured);
  }

  private static ClaimFacts claimFacts(
      JsonNode c, List<JsonNode> docs, List<LocalDate> earlier, boolean seenBefore) {
    Set<DocumentType> types = EnumSet.noneOf(DocumentType.class);
    List<LocalDate> dates = new ArrayList<>();
    RepairFacts invoice = null;
    RepairFacts estimate = null;
    for (JsonNode d : docs) {
      DocumentType type = DocumentType.valueOf(d.get("document_type").asText());
      types.add(type);
      if (d.hasNonNull("repair")) {
        JsonNode r = d.get("repair");
        dates.add(LocalDate.parse(r.get("issue_date").asText()));
        List<BigDecimal> lines = new ArrayList<>();
        r.get("items").forEach(i -> lines.add(new BigDecimal(i.get("amount").asText())));
        RepairFacts facts =
            new RepairFacts(
                r.at("/issuer/tax_id").asText(),
                r.get("number").asText(),
                LocalDate.parse(r.get("issue_date").asText()),
                lines,
                new BigDecimal(r.get("tax_rate").asText()),
                new BigDecimal(r.get("total").asText()));
        if (type == DocumentType.INVOICE) {
          invoice = facts;
        } else {
          estimate = facts;
        }
      }
      if (d.hasNonNull("police_report")) {
        dates.add(LocalDate.parse(d.at("/police_report/filed_date").asText()));
      }
      if (d.hasNonNull("accident_report")) {
        dates.add(LocalDate.parse(d.at("/accident_report/report_date").asText()));
      }
    }
    return new ClaimFacts(
        c.get("claim_id").asText(),
        CoverageCode.valueOf(c.get("claim_type").asText()),
        LocalDate.parse(c.get("incident_date").asText()),
        LocalDate.parse(c.get("reported_date").asText()),
        types,
        dates,
        Optional.ofNullable(invoice != null ? invoice : estimate),
        earlier,
        seenBefore);
  }

  /** The proposal a perfect set of agents would make for this claim. */
  private static Proposal proposal(JsonNode exp) {
    Decision decision = Decision.valueOf(exp.get("decision").asText());
    BigDecimal eligible =
        decision == Decision.APPROVE
            ? new BigDecimal(exp.get("eligible_amount").asText()).setScale(2, RoundingMode.HALF_UP)
            : null;
    String exclusion = exp.hasNonNull("exclusion_code") ? exp.get("exclusion_code").asText() : null;
    List<String> citations = new ArrayList<>();
    exp.get("citations").forEach(n -> citations.add(n.asText()));
    List<FraudSignal> signals = new ArrayList<>();
    exp.get("fraud_signals")
        .forEach(
            n -> {
              // Only the description mismatch needs a model; the rules derive every other signal.
              if (FraudSignalType.valueOf(n.asText()) == FraudSignalType.DESCRIPTION_MISMATCH) {
                signals.add(
                    new FraudSignal(
                        FraudSignalType.DESCRIPTION_MISMATCH,
                        "Invoice items do not match the description",
                        1.0,
                        SignalSource.MODEL));
              }
            });
    return new Proposal(decision, eligible, null, exclusion, citations, signals);
  }

  private static List<JsonNode> read(String file) throws IOException {
    List<JsonNode> nodes = new ArrayList<>();
    JSON.readTree(Files.readString(DATASET.resolve(file))).forEach(nodes::add);
    return nodes;
  }

  private static Map<String, JsonNode> index(List<JsonNode> nodes, String key) {
    Map<String, JsonNode> map = new HashMap<>();
    nodes.forEach(n -> map.put(n.get(key).asText(), n));
    return map;
  }
}
