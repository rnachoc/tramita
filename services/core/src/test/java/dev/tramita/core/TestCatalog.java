package dev.tramita.core;

import dev.tramita.core.catalog.Catalog;
import dev.tramita.core.catalog.CatalogLoader;
import dev.tramita.core.catalog.ClauseIndex;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** The real product catalog and clause index from {@code data/policies}, for tests. */
public final class TestCatalog {

  public static final Path POLICIES = Path.of("..", "..", "data", "policies");
  public static final Catalog CATALOG = load("catalog.yaml", true);
  public static final ClauseIndex CLAUSES = loadClauses();

  private TestCatalog() {}

  private static Catalog load(String file, boolean yaml) {
    try (InputStream in = Files.newInputStream(POLICIES.resolve(file))) {
      return CatalogLoader.catalog(in);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  private static ClauseIndex loadClauses() {
    try (InputStream in = Files.newInputStream(POLICIES.resolve("clauses.json"))) {
      return CatalogLoader.clauses(in);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }
}
