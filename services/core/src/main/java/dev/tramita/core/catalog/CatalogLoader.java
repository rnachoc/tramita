package dev.tramita.core.catalog;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import java.io.IOException;
import java.io.InputStream;
import java.util.List;

/**
 * Parses the product catalog (YAML) and the clause index (JSON).
 *
 * <p>Parsing is strict: an unknown field fails instead of being ignored, so a catalog change the
 * Java code does not understand cannot silently change behaviour.
 */
public final class CatalogLoader {

  private CatalogLoader() {}

  public static Catalog catalog(InputStream yaml) throws IOException {
    ObjectMapper mapper = strict(new ObjectMapper(new YAMLFactory()));
    SimpleModule limits = new SimpleModule();
    limits.addDeserializer(Catalog.Limit.class, new LimitDeserializer());
    mapper.registerModule(limits);
    return mapper.readValue(yaml, Catalog.class);
  }

  public static ClauseIndex clauses(InputStream json) throws IOException {
    List<Clause> clauses = strict(new ObjectMapper()).readValue(json, new TypeReference<>() {});
    return new ClauseIndex(clauses);
  }

  private static ObjectMapper strict(ObjectMapper mapper) {
    return mapper
        .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
  }

  /** Accepts either an amount or the literal {@code insured_value}. */
  private static final class LimitDeserializer extends JsonDeserializer<Catalog.Limit> {
    @Override
    public Catalog.Limit deserialize(JsonParser parser, DeserializationContext context)
        throws IOException {
      return Catalog.Limit.parse(parser.getValueAsString());
    }
  }
}
