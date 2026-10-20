package dev.tramita.core.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Who may call what. The split between AGENT and REVIEWER is the trust boundary of the system: the
 * agent service can propose but never approve, correct, reject or pay.
 */
@Configuration
public class SecurityConfiguration {

  private static final String AGENT = Role.AGENT.name();
  private static final String REVIEWER = Role.REVIEWER.name();
  private static final String ANALYST = Role.ANALYST.name();
  private static final String ADMIN = Role.ADMIN.name();

  @Bean
  ApiKeyRegistry apiKeyRegistry(@Value("${tramita.security.api-keys:}") String keys) {
    return new ApiKeyRegistry(keys);
  }

  @Bean
  SecurityFilterChain api(HttpSecurity http, ApiKeyRegistry registry) throws Exception {
    return http.csrf(AbstractHttpConfigurer::disable)
        .httpBasic(AbstractHttpConfigurer::disable)
        .formLogin(AbstractHttpConfigurer::disable)
        .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .exceptionHandling(
            e -> e.authenticationEntryPoint(new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
        .addFilterBefore(
            new ApiKeyAuthenticationFilter(registry), UsernamePasswordAuthenticationFilter.class)
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers("/actuator/health/**", "/actuator/info")
                    .permitAll()
                    .requestMatchers(HttpMethod.POST, "/api/import/**")
                    .hasRole(ADMIN)
                    .requestMatchers(HttpMethod.POST, "/api/claims/*/reviews")
                    .hasRole(REVIEWER)
                    .requestMatchers(HttpMethod.POST, "/api/claims", "/api/claims/**")
                    .hasRole(AGENT)
                    .requestMatchers(HttpMethod.PUT, "/api/claims/*/documents/**")
                    .hasRole(AGENT)
                    .requestMatchers(HttpMethod.GET, "/api/**")
                    .hasAnyRole(AGENT, REVIEWER, ANALYST, ADMIN)
                    .anyRequest()
                    .denyAll())
        .build();
  }
}
