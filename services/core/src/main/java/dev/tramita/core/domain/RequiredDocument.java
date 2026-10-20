package dev.tramita.core.domain;

import java.util.Set;

/** Documents a guarantee requires before a claim can be assessed. */
public enum RequiredDocument {
  REPAIR_INVOICE_OR_ESTIMATE,
  POLICE_REPORT,
  ACCIDENT_REPORT;

  /** Whether the documents received so far satisfy this requirement. */
  public boolean isSatisfiedBy(Set<DocumentType> received) {
    return switch (this) {
      case REPAIR_INVOICE_OR_ESTIMATE ->
          received.contains(DocumentType.INVOICE) || received.contains(DocumentType.ESTIMATE);
      case POLICE_REPORT -> received.contains(DocumentType.POLICE_REPORT);
      // A friendly accident report or a police record both document an accident.
      case ACCIDENT_REPORT ->
          received.contains(DocumentType.ACCIDENT_REPORT)
              || received.contains(DocumentType.POLICE_REPORT);
    };
  }
}
