package dev.tramita.core.events;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.tramita.core.audit.AuditEvent;
import java.io.IOException;
import java.nio.file.Path;
import java.time.Instant;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * The relay against the event contract the consumers are written to: the JSON Schema generated from
 * the Python models ({@code make event-schemas}).
 */
class ClaimEventContractTest {

  private static final Path SCHEMA = Path.of("../../docs/events/claim-event.schema.json");

  private static JsonNode schema() throws IOException {
    return new ObjectMapper().readTree(SCHEMA.toFile());
  }

  private static Set<String> names(JsonNode properties) {
    Set<String> names = new HashSet<>();
    properties.fieldNames().forEachRemaining(names::add);
    return names;
  }

  @Test
  void everyPublishedTypeHasExactlyTheFieldsOfItsContract() throws IOException {
    JsonNode data = schema().get("data");

    assertThat(names(data)).isEqualTo(ClaimEvents.PUBLIC_FIELDS.keySet());
    ClaimEvents.PUBLIC_FIELDS.forEach(
        (type, fields) ->
            assertThat(names(data.get(type).get("properties"))).as(type).isEqualTo(fields));
  }

  @Test
  void theEnvelopeHasExactlyTheFieldsOfItsContract() throws IOException {
    AuditEvent e =
        new AuditEvent("CL-1", Instant.EPOCH, "agents", "AGENT", "CLAIM_RECEIVED", Map.of());
    ReflectionTestUtils.setField(e, "eventId", 1L);
    JsonNode envelope = schema().get("envelope");

    assertThat(ClaimEvents.envelope(e).keySet())
        .isEqualTo(names(envelope.get("properties")))
        .containsAll(
            new ObjectMapper().convertValue(envelope.get("required"), java.util.List.class));
  }
}
