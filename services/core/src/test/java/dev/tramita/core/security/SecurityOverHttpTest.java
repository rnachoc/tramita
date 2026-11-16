package dev.tramita.core.security;

import static org.assertj.core.api.Assertions.assertThat;

import dev.tramita.core.api.PostgresTestConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

/**
 * Status codes through a real servlet container. MockMvc does not forward errors to /error, so it
 * cannot see how the security chain treats that second dispatch.
 */
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties =
        "tramita.security.api-keys=agents:AGENT:agent-change-me-local-only;"
            + "analyst:ANALYST:analyst-change-me-local-only")
@Import(PostgresTestConfiguration.class)
class SecurityOverHttpTest {

  @Autowired private TestRestTemplate http;

  private ResponseEntity<String> review(String key) {
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("Idempotency-Key", "r-1");
    if (key != null) {
      headers.set("X-Api-Key", key);
    }
    return http.exchange(
        "/api/claims/CL-1/reviews",
        HttpMethod.POST,
        new HttpEntity<>("{\"reviewer\": \"x\", \"action\": \"APPROVE\"}", headers),
        String.class);
  }

  @Test
  void aKnownKeyWithoutTheRoleIsForbiddenNotUnauthenticated() {
    assertThat(review("analyst-change-me-local-only").getStatusCode())
        .isEqualTo(HttpStatus.FORBIDDEN);
    assertThat(review("agent-change-me-local-only").getStatusCode())
        .isEqualTo(HttpStatus.FORBIDDEN);
  }

  @Test
  void noKeyOrAnUnknownKeyIsUnauthenticated() {
    assertThat(review(null).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    assertThat(review("not-a-key-of-this-core").getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
  }
}
