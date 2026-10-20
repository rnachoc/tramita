package dev.tramita.core.web;

/** The requested resource does not exist. Mapped to 404. */
public class NotFoundException extends RuntimeException {

  public NotFoundException(String message) {
    super(message);
  }
}
