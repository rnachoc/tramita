package dev.tramita.core.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/** The authenticated client of the current request, for audit records. */
public final class CurrentActor {

  private CurrentActor() {}

  public static ApiClient get() {
    Authentication auth = SecurityContextHolder.getContext().getAuthentication();
    if (auth != null && auth.getPrincipal() instanceof ApiClient client) {
      return client;
    }
    return new ApiClient("system", Role.ADMIN);
  }
}
