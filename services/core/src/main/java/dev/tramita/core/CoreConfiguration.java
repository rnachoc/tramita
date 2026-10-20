package dev.tramita.core;

import dev.tramita.core.catalog.Catalog;
import dev.tramita.core.catalog.ClauseIndex;
import dev.tramita.core.rules.RulesEngine;
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Wires framework-free domain components into the application. */
@Configuration
public class CoreConfiguration {

  @Bean
  Clock clock() {
    return Clock.systemUTC();
  }

  @Bean
  RulesEngine rulesEngine(Catalog catalog, ClauseIndex clauses) {
    return new RulesEngine(catalog, clauses);
  }
}
