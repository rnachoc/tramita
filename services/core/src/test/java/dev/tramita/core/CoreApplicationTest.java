package dev.tramita.core;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class CoreApplicationTest {

  @Autowired private TestRestTemplate http;

  @Test
  void healthEndpointReportsUp() {
    String body = http.getForObject("/actuator/health", String.class);

    assertThat(body).contains("\"status\":\"UP\"");
  }
}
