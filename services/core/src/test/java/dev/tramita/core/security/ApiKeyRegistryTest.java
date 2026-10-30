package dev.tramita.core.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class ApiKeyRegistryTest {

  private final ApiKeyRegistry registry =
      new ApiKeyRegistry(
          "agents:AGENT:agent-change-me-local-only; console:REVIEWER:console-change-me-local-only");

  @Test
  void identifiesTheClientOfAKnownKey() {
    assertThat(registry.authenticate("console-change-me-local-only"))
        .contains(new ApiClient("console", Role.REVIEWER));
  }

  @Test
  void rejectsUnknownAndEmptyKeys() {
    assertThat(registry.authenticate("nope")).isEmpty();
    assertThat(registry.authenticate("")).isEmpty();
    assertThat(registry.authenticate(null)).isEmpty();
  }

  @Test
  void refusesShortKeysAtStartUp() {
    assertThatThrownBy(() -> new ApiKeyRegistry("agents:AGENT:short"))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void noConfigurationMeansNoClients() {
    assertThat(new ApiKeyRegistry("").size()).isZero();
  }
}
