package dev.tramita.core.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;

/** Loads the product catalog and the clause index packaged from {@code data/policies}. */
@Configuration
public class CatalogConfiguration {

  @Bean
  Catalog catalog(@Value("${tramita.catalog.location}") Resource location) {
    try (InputStream in = location.getInputStream()) {
      return CatalogLoader.catalog(in);
    } catch (IOException e) {
      throw new UncheckedIOException("cannot read the product catalog " + location, e);
    }
  }

  @Bean
  ClauseIndex clauseIndex(@Value("${tramita.catalog.clauses}") Resource location) {
    try (InputStream in = location.getInputStream()) {
      return CatalogLoader.clauses(in);
    } catch (IOException e) {
      throw new UncheckedIOException("cannot read the clause index " + location, e);
    }
  }
}
