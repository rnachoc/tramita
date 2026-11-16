package dev.tramita.core.events;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.tramita.core.api.PostgresTestConfiguration;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.kafka.KafkaConnectionDetails;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.kafka.KafkaContainer;

/** The relay against real PostgreSQL and Kafka: committed changes come out as ordered events. */
@SpringBootTest(
    properties = {
      "tramita.security.api-keys=agents:AGENT:agent-change-me-local-only;"
          + "admin:ADMIN:admin-change-me-local-only",
      "tramita.events.enabled=true",
      "tramita.events.relay-interval-ms=100"
    })
@AutoConfigureMockMvc
@Import({PostgresTestConfiguration.class, ClaimEventsKafkaTest.KafkaTestConfiguration.class})
class ClaimEventsKafkaTest {

  private static final String AGENT = "agent-change-me-local-only";
  private static final String ADMIN = "admin-change-me-local-only";

  @TestConfiguration(proxyBeanMethods = false)
  static class KafkaTestConfiguration {
    @Bean
    @ServiceConnection
    KafkaContainer kafka() {
      // The same image as Docker Compose.
      return new KafkaContainer("apache/kafka:4.2.2");
    }
  }

  @Autowired private MockMvc http;
  @Autowired private ObjectMapper json;
  @Autowired private KafkaConnectionDetails kafkaConnection;

  @Test
  void aRegisteredClaimIsPublishedInOrderWithoutPersonalData() throws Exception {
    http.perform(
            post("/api/import/policies")
                .header("X-Api-Key", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"policyholders": [{"holder_id": "PH-0001", "full_name": "Lucía Prueba Sintética",
                      "nif": "12345678Z", "birth_date": "1985-04-02", "email": "lucia@correo.example",
                      "phone": "+34 600 000 001", "iban": "ES91 9999 0000 0000 0000 0001",
                      "address": {"street": "Calle Ficticia, 1", "postal_code": "41001", "city": "Sevilla", "province": "Sevilla"}}],
                     "policies": [{"policy_number": "BR-HP-000001", "holder_id": "PH-0001", "product_code": "HP",
                      "line": "HOME", "start_date": "2026-01-01", "end_date": "2026-12-31", "annual_premium": 230.00}]}
                    """))
        .andExpect(status().isOk());
    http.perform(
            post("/api/claims")
                .header("X-Api-Key", AGENT)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"claim_id": "CL-E00001", "policy_number": "BR-HP-000001", "reported_date": "2026-05-12",
                     "incident_date": "2026-05-10", "claim_type": "HOME_WATER", "location": "Calle Ficticia, 1",
                     "description": "Soy Lucía Prueba Sintética y se ha roto una tubería.",
                     "contact_phone": "+34 600 000 001", "claimed_amount": 1210.00}
                    """))
        .andExpect(status().isCreated());
    http.perform(
            post("/api/claims/{id}/documents", "CL-E00001")
                .header("X-Api-Key", AGENT)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"document_id": "DOC-E1", "document_type": "INVOICE", "filename": "f.pdf", "storage_key": "k"}
                    """))
        .andExpect(status().isCreated());

    List<ConsumerRecord<String, String>> records = consume(2, Duration.ofSeconds(30));

    assertThat(records).extracting(ConsumerRecord::key).containsOnly("CL-E00001");
    List<JsonNode> events = new ArrayList<>();
    for (ConsumerRecord<String, String> r : records) {
      assertThat(r.value()).doesNotContain("Lucía", "600 000 001", "tubería", "12345678Z");
      events.add(json.readTree(r.value()));
    }
    assertThat(events)
        .extracting(e -> e.get("event_type").asText())
        .containsExactly("CLAIM_RECEIVED", "DOCUMENT_RECEIVED");
    JsonNode first = events.get(0);
    assertThat(first.get("schema_version").asInt()).isEqualTo(1);
    assertThat(first.get("actor_role").asText()).isEqualTo("AGENT");
    assertThat(json.convertValue(first.get("data"), Map.class))
        .isEqualTo(Map.of("policy_number", "BR-HP-000001", "claim_type", "HOME_WATER"));
    assertThat(Long.parseLong(events.get(1).get("event_id").asText()))
        .isGreaterThan(Long.parseLong(first.get("event_id").asText()));
  }

  private List<ConsumerRecord<String, String>> consume(int wanted, Duration timeout) {
    Map<String, Object> config =
        Map.of(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            String.join(",", kafkaConnection.getBootstrapServers()),
            ConsumerConfig.GROUP_ID_CONFIG,
            "test-" + UUID.randomUUID(),
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest");
    List<ConsumerRecord<String, String>> records = new ArrayList<>();
    try (KafkaConsumer<String, String> consumer =
        new KafkaConsumer<>(config, new StringDeserializer(), new StringDeserializer())) {
      consumer.subscribe(List.of("tramita.claim-events"));
      long deadline = System.currentTimeMillis() + timeout.toMillis();
      while (records.size() < wanted && System.currentTimeMillis() < deadline) {
        consumer.poll(Duration.ofMillis(500)).forEach(records::add);
      }
    }
    return records;
  }
}
