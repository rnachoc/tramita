package dev.tramita.core.web;

/**
 * The request contradicts the current state, for example reviewing a closed claim. Mapped to 409.
 */
public class ConflictException extends RuntimeException {

  public ConflictException(String message) {
    super(message);
  }
}
