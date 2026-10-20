package dev.tramita.core.security;

/** What a client of the core API may do. */
public enum Role {
  /** The agent service: registers claims and documents, submits proposals. Cannot review. */
  AGENT,
  /** A claims handler, through the review console: approves, corrects or rejects proposals. */
  REVIEWER,
  /** Read-only access for analysts, for example through the MCP server. */
  ANALYST,
  /** Loads reference data such as policies. */
  ADMIN;

  public String authority() {
    return "ROLE_" + name();
  }
}
