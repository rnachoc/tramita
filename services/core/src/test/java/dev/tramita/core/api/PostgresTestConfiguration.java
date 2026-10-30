package dev.tramita.core.api;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/** A real PostgreSQL (the same image as Docker Compose) for integration tests. */
@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfiguration {

  static final DockerImageName IMAGE =
      DockerImageName.parse("pgvector/pgvector:0.8.7-pg17-trixie")
          .asCompatibleSubstituteFor("postgres");

  @Bean
  @ServiceConnection
  PostgreSQLContainer<?> postgres() {
    return new PostgreSQLContainer<>(IMAGE);
  }
}
