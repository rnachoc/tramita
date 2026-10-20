package dev.tramita.core.security;

/** A client authenticated by API key. */
public record ApiClient(String name, Role role) {}
