package dev.tramita.core.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/** Authenticates requests carrying an {@code X-Api-Key} header. */
public class ApiKeyAuthenticationFilter extends OncePerRequestFilter {

  public static final String HEADER = "X-Api-Key";

  private final ApiKeyRegistry registry;

  public ApiKeyAuthenticationFilter(ApiKeyRegistry registry) {
    this.registry = registry;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    registry
        .authenticate(request.getHeader(HEADER))
        .ifPresent(
            client -> {
              var authorities = List.of(new SimpleGrantedAuthority(client.role().authority()));
              var authentication =
                  new UsernamePasswordAuthenticationToken(client, null, authorities);
              SecurityContextHolder.getContext().setAuthentication(authentication);
            });
    chain.doFilter(request, response);
  }
}
