package dev.tramita.core.rules;

/** A point where the proposal contradicts the rules. Any violation sends the claim to a human. */
public record Violation(String code, String message) {}
