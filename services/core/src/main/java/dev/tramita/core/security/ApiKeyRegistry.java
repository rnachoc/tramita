package dev.tramita.core.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * API keys and the client each one identifies, parsed from configuration of the form {@code
 * name:ROLE:key;name:ROLE:key}. Keys are compared in constant time and never logged.
 */
public final class ApiKeyRegistry {

  private record Entry(ApiClient client, byte[] key) {}

  private final List<Entry> entries = new ArrayList<>();

  public ApiKeyRegistry(String configuration) {
    if (configuration == null || configuration.isBlank()) {
      return;
    }
    for (String item : configuration.split(";")) {
      String[] parts = item.trim().split(":", 3);
      if (parts.length != 3 || parts[2].length() < 16) {
        throw new IllegalArgumentException(
            "API keys must look like name:ROLE:key with keys of at least 16 characters");
      }
      ApiClient client = new ApiClient(parts[0], Role.valueOf(parts[1]));
      entries.add(new Entry(client, parts[2].getBytes(StandardCharsets.UTF_8)));
    }
  }

  public Optional<ApiClient> authenticate(String presentedKey) {
    if (presentedKey == null || presentedKey.isEmpty()) {
      return Optional.empty();
    }
    byte[] presented = presentedKey.getBytes(StandardCharsets.UTF_8);
    ApiClient match = null;
    for (Entry entry : entries) {
      // Compare against every key so timing does not reveal which one matched.
      if (MessageDigest.isEqual(entry.key(), presented)) {
        match = entry.client();
      }
    }
    return Optional.ofNullable(match);
  }

  public int size() {
    return entries.size();
  }
}
