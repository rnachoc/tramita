package dev.tramita.core.catalog;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

/**
 * Lookup of policy clauses by id and by semantic key (for example {@code exclusion:AUTO_ALCOHOL}).
 *
 * <p>The rules engine uses it to reject citations that do not exist or that belong to another
 * product, and to require the clause that grounds each decision.
 */
public final class ClauseIndex {

  private final Map<String, Clause> byId = new HashMap<>();
  private final Map<String, String> byProductAndKey = new HashMap<>();

  public ClauseIndex(Collection<Clause> clauses) {
    for (Clause clause : clauses) {
      byId.put(clause.clauseId(), clause);
      for (String key : clause.keys()) {
        byProductAndKey.put(clause.productCode() + "|" + key, clause.clauseId());
      }
    }
  }

  public Optional<Clause> find(String clauseId) {
    return Optional.ofNullable(byId.get(clauseId));
  }

  /** Whether the clause exists and belongs to the given product. */
  public boolean belongsTo(String clauseId, String productCode) {
    return find(clauseId).map(c -> c.productCode().equals(productCode)).orElse(false);
  }

  /**
   * The clause id that grounds a semantic key in a product, such as {@code coverage:HOME_WATER}.
   */
  public Optional<String> clauseFor(String productCode, String key) {
    return Optional.ofNullable(byProductAndKey.get(productCode + "|" + key));
  }

  public int size() {
    return byId.size();
  }
}
