package dev.tramita.core.catalog;

import java.util.List;

/** One clause of the policy conditions, as published in {@code data/policies/clauses.json}. */
public record Clause(
    String clauseId,
    String productCode,
    String productName,
    String article,
    String title,
    String text,
    List<String> keys) {}
