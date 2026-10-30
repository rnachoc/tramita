package dev.tramita.core.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

/** End-to-end tests of the core API against a real PostgreSQL. */
@SpringBootTest(
    properties =
        "tramita.security.api-keys=agents:AGENT:agent-change-me-local-only;"
            + "console:REVIEWER:review-change-me-local-only;admin:ADMIN:admin-change-me-local-only;"
            + "analyst:ANALYST:analyst-change-me-local-only")
@AutoConfigureMockMvc
@Import(PostgresTestConfiguration.class)
class ClaimApiTest {

  private static final String AGENT = "agent-change-me-local-only";
  private static final String REVIEWER = "review-change-me-local-only";
  private static final String ADMIN = "admin-change-me-local-only";
  private static final String ANALYST = "analyst-change-me-local-only";
  private static final AtomicInteger SEQUENCE = new AtomicInteger();

  @Autowired private MockMvc http;
  @Autowired private ObjectMapper json;
  @Autowired private JdbcTemplate jdbc;

  @BeforeEach
  void importPolicies() throws Exception {
    String body =
        """
        {
          "policyholders": [{
            "holder_id": "PH-0001", "full_name": "Lucía Prueba Sintética", "nif": "12345678Z",
            "birth_date": "1985-04-02", "email": "lucia@correo.example", "phone": "+34 600 000 001",
            "address": {"street": "Calle Ficticia, 1", "postal_code": "41001", "city": "Sevilla", "province": "Sevilla"},
            "iban": "ES91 9999 0000 0000 0000 0001"
          }],
          "policies": [
            {"policy_number": "BR-HP-000001", "holder_id": "PH-0001", "product_code": "HP", "line": "HOME",
             "start_date": "2026-01-01", "end_date": "2026-12-31", "annual_premium": 230.00},
            {"policy_number": "BR-HB-000002", "holder_id": "PH-0001", "product_code": "HB", "line": "HOME",
             "start_date": "2026-01-01", "end_date": "2026-12-31", "annual_premium": 140.00}
          ]
        }
        """;
    http.perform(
            post("/api/import/policies")
                .header("X-Api-Key", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
        .andExpect(status().isOk());
  }

  // --- helpers ----------------------------------------------------------------------------------

  private String newClaim(String policy, String type) throws Exception {
    String id = "CL-T%05d".formatted(SEQUENCE.incrementAndGet());
    String body =
        """
        {"claim_id": "%s", "policy_number": "%s", "reported_date": "2026-05-12", "incident_date": "2026-05-10",
         "claim_type": "%s", "location": "Calle Ficticia, 1", "description": "Se ha roto una tubería en la cocina.",
         "claimed_amount": 1210.00}
        """
            .formatted(id, policy, type);
    agent(post("/api/claims").content(body)).andExpect(status().isCreated());
    return id;
  }

  /** Attaches an invoice with two lines adding up to {@code net} plus 21% tax. */
  private void invoice(String claimId, String net, String number) throws Exception {
    String doc = claimId + "-D";
    agent(
            post("/api/claims/{id}/documents", claimId)
                .content(
                    """
                    {"document_id": "%s", "document_type": "INVOICE", "filename": "factura.pdf", "storage_key": "claims/%s/factura.pdf"}
                    """
                        .formatted(doc, claimId)))
        .andExpect(status().isCreated());
    double total = Double.parseDouble(net);
    double first = Math.round(total * 0.6 * 100) / 100.0 + 0.37;
    String extraction =
        String.format(
            Locale.ROOT,
            """
            {"fields": {"customer_name": "<PERSON>"}, "issue_date": "2026-05-11", "issuer_tax_id": "B12345674",
             "document_number": "%s", "stated_total": %.2f, "tax_rate": 21,
             "line_amounts": [%.2f, %.2f]}
            """,
            number,
            total * 1.21,
            first,
            total - first);
    agent(put("/api/claims/{id}/documents/{doc}/extraction", claimId, doc).content(extraction))
        .andExpect(status().isOk());
  }

  private JsonNode propose(String claimId, String key, String body) throws Exception {
    String response =
        agent(
                post("/api/claims/{id}/proposals", claimId)
                    .header("Idempotency-Key", key)
                    .content(body))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    return json.readTree(response);
  }

  private static String approval(String eligible, String citation) {
    return """
    {"decision": "APPROVE", "eligible_amount": %s, "proposed_amount": %s, "citations": ["%s"],
     "fraud_signals": [], "rationale": "Escape de agua accidental cubierto por la garantía."}
    """
        .formatted(eligible, eligible, citation);
  }

  private ResultActions agent(
      org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request)
      throws Exception {
    return http.perform(request.header("X-Api-Key", AGENT).contentType(MediaType.APPLICATION_JSON));
  }

  private ResultActions reviewer(String claimId, String key, String body) throws Exception {
    return http.perform(
        post("/api/claims/{id}/reviews", claimId)
            .header("X-Api-Key", REVIEWER)
            .header("Idempotency-Key", key)
            .contentType(MediaType.APPLICATION_JSON)
            .content(body));
  }

  private List<String> auditTypes(String claimId) throws Exception {
    String body =
        http.perform(get("/api/claims/{id}/audit", claimId).header("X-Api-Key", ANALYST))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    List<String> types = new ArrayList<>();
    json.readTree(body).forEach(e -> types.add(e.get("event_type").asText()));
    return types;
  }

  // --- tests
  // ----------------------------------------------------------------------------------------

  @Test
  void coveredClaimIsPaidAutomaticallyExactlyOnce() throws Exception {
    String claim = newClaim("BR-HP-000001", "HOME_WATER");
    invoice(claim, "1000.00", "F-" + claim);

    JsonNode first = propose(claim, "p-" + claim, approval("1210.00", "HP-2.1"));
    JsonNode replay = propose(claim, "p-" + claim, approval("1210.00", "HP-2.1"));

    assertThat(first.at("/proposal/routing").asText()).isEqualTo("AUTO");
    assertThat(first.at("/claim_status").asText()).isEqualTo("PAID");
    assertThat(first.at("/payment/amount").decimalValue()).isEqualByComparingTo("1110.00");
    assertThat(first.at("/payment/iban_masked").asText()).endsWith("0001").doesNotContain("9999");
    assertThat(replay.at("/proposal/proposal_id")).isEqualTo(first.at("/proposal/proposal_id"));
    assertThat(
            jdbc.queryForObject(
                "select count(*) from core.payments where claim_id = ?", Integer.class, claim))
        .isEqualTo(1);
    // Evidence is frozen once the claim is decided.
    agent(
            post("/api/claims/{id}/documents", claim)
                .content(
                    "{\"document_id\": \"LATE-"
                        + claim
                        + "\", \"document_type\": \"INVOICE\", \"filename\": \"otra.pdf\"}"))
        .andExpect(status().isConflict());
    assertThat(auditTypes(claim))
        .containsExactly(
            "CLAIM_RECEIVED",
            "DOCUMENT_RECEIVED",
            "DOCUMENT_EXTRACTED",
            "PROPOSAL_EVALUATED",
            "PAYMENT_EXECUTED");
  }

  @Test
  void largePaymentWaitsForAHumanAndOnlyAReviewerCanApprove() throws Exception {
    String claim = newClaim("BR-HP-000001", "HOME_WATER");
    invoice(claim, "4000.00", "F-" + claim);

    JsonNode proposal = propose(claim, "p-" + claim, approval("4840.00", "HP-2.1"));
    assertThat(proposal.at("/proposal/routing").asText()).isEqualTo("HUMAN_REVIEW");
    assertThat(proposal.at("/claim_status").asText()).isEqualTo("PENDING_REVIEW");
    assertThat(proposal.at("/payment").isMissingNode()).isTrue();

    // The agent service cannot approve its own proposal.
    http.perform(
            post("/api/claims/{id}/reviews", claim)
                .header("X-Api-Key", AGENT)
                .header("Idempotency-Key", "r-agent")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reviewer\": \"agent\", \"action\": \"APPROVE\"}"))
        .andExpect(status().isForbidden());

    // A human cannot pay above the guarantee limit either.
    reviewer(
            claim,
            "r-too-much-" + claim,
            """
            {"reviewer": "marta", "action": "CORRECT", "decision": "APPROVE", "amount": 20000, "comment": "Peritación"}
            """)
        .andExpect(status().isBadRequest());

    reviewer(claim, "r-" + claim, "{\"reviewer\": \"marta\", \"action\": \"APPROVE\"}")
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.claim_status").value("PAID"))
        .andExpect(jsonPath("$.payment.amount").value(4740.00))
        .andExpect(jsonPath("$.payment.triggered_by").value("REVIEW"));
  }

  @Test
  void productWithoutTheGuaranteeIsRejectedOnlyByAHuman() throws Exception {
    String claim = newClaim("BR-HB-000002", "HOME_GLASS");
    invoice(claim, "300.00", "F-" + claim);

    JsonNode proposal = propose(claim, "p-" + claim, approval("363.00", "HB-2.1"));

    assertThat(proposal.at("/proposal/decision").asText()).isEqualTo("REJECT");
    assertThat(proposal.at("/proposal/routing").asText()).isEqualTo("HUMAN_REVIEW");
    assertThat(proposal.at("/proposal/violations/0/code").asText())
        .isEqualTo("DECISION_OVERRIDDEN");

    reviewer(claim, "r-" + claim, "{\"reviewer\": \"marta\", \"action\": \"REJECT\"}")
        .andExpect(status().isBadRequest()); // a rejection needs a comment
    reviewer(
            claim,
            "r2-" + claim,
            "{\"reviewer\": \"marta\", \"action\": \"REJECT\", \"comment\": \"El producto no"
                + " incluye cristales.\"}")
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.claim_status").value("REJECTED"));

    // Closed claims accept no further proposals.
    agent(
            post("/api/claims/{id}/proposals", claim)
                .header("Idempotency-Key", "p2-" + claim)
                .content(approval("363.00", "HB-2.1")))
        .andExpect(status().isConflict());
  }

  @Test
  void requestsWithoutAValidKeyAreRefused() throws Exception {
    http.perform(get("/api/claims")).andExpect(status().isUnauthorized());
    http.perform(get("/api/claims").header("X-Api-Key", "wrong-change-me-local-only"))
        .andExpect(status().isUnauthorized());
    http.perform(
            post("/api/import/policies")
                .header("X-Api-Key", AGENT)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"policyholders\": [], \"policies\": []}"))
        .andExpect(status().isForbidden());
  }

  @Test
  void registeringTheSameClaimTwiceIsIdempotentButConflictingContentIsRejected() throws Exception {
    String body =
        """
        {"claim_id": "CL-IDEM1", "policy_number": "BR-HP-000001", "reported_date": "2026-05-12",
         "incident_date": "2026-05-10", "claim_type": "HOME_WATER", "location": "Casa", "description": "Fuga."}
        """;
    agent(post("/api/claims").content(body)).andExpect(status().isCreated());
    agent(post("/api/claims").content(body)).andExpect(status().isCreated());
    agent(post("/api/claims").content(body.replace("Fuga.", "Otra cosa.")))
        .andExpect(status().isConflict());
  }

  @Test
  void auditTrailIsAppendOnly() throws Exception {
    String claim = newClaim("BR-HP-000001", "HOME_WATER");

    assertThatThrownBy(
            () -> jdbc.update("update core.audit_events set actor = 'x' where claim_id = ?", claim))
        .hasMessageContaining("append-only");
    assertThatThrownBy(() -> jdbc.update("delete from core.audit_events where claim_id = ?", claim))
        .hasMessageContaining("append-only");
  }

  @Test
  void healthIsPublic() throws Exception {
    http.perform(get("/actuator/health")).andExpect(status().isOk());
  }

  @Test
  void malformedBodiesAreExplainedFieldByField() throws Exception {
    agent(post("/api/claims").content("{\"claim_id\": \"CL-X\", \"colour\": \"red\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.detail")
                .value(org.hamcrest.Matchers.containsString("Unknown field 'colour'")));
    agent(post("/api/claims").content("{\"claim_id\": \"CL-X\", \"claim_type\": \"FLOOD\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.detail")
                .value(org.hamcrest.Matchers.containsString("allowed values: HOME_WATER")));
    http.perform(get("/api/claims").param("status", "LOST").header("X-Api-Key", ANALYST))
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.detail").value(org.hamcrest.Matchers.containsString("parameter 'status'")));
  }

  @Test
  void validationErrorsExplainWhatToFix() throws Exception {
    agent(post("/api/claims").content("{\"claim_id\": \"CL-X\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.detail").value(org.hamcrest.Matchers.containsString("policy_number")));
  }
}
