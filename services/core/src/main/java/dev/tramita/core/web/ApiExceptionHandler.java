package dev.tramita.core.web;

import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.exc.InvalidFormatException;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import dev.tramita.core.claim.ClaimClosedException;
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

/**
 * Maps errors to RFC 9457 problem details. Messages are written so that a calling agent can
 * understand what was wrong and correct its next request.
 */
@RestControllerAdvice
public class ApiExceptionHandler {

  @ExceptionHandler(NotFoundException.class)
  ProblemDetail notFound(NotFoundException e) {
    return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, e.getMessage());
  }

  @ExceptionHandler({ConflictException.class, ClaimClosedException.class})
  ProblemDetail conflict(RuntimeException e) {
    return ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT, e.getMessage());
  }

  @ExceptionHandler(ObjectOptimisticLockingFailureException.class)
  ProblemDetail concurrentUpdate(ObjectOptimisticLockingFailureException e) {
    return ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "The claim was modified by another request at the same time. Reload it and retry.");
  }

  /** Malformed JSON, unknown fields and invalid enum values, explained field by field. */
  @ExceptionHandler(HttpMessageNotReadableException.class)
  ProblemDetail unreadable(HttpMessageNotReadableException e) {
    String detail = "The request body is not valid JSON for this endpoint.";
    if (e.getCause() instanceof UnrecognizedPropertyException u) {
      detail = "Unknown field '" + path(u) + "'. Remove it; the API does not accept extra fields.";
    } else if (e.getCause() instanceof InvalidFormatException f) {
      detail =
          "Invalid value '"
              + f.getValue()
              + "' for field '"
              + path(f)
              + "'"
              + allowed(f.getTargetType())
              + ".";
    } else if (e.getCause() instanceof JsonMappingException m && !m.getPath().isEmpty()) {
      detail = "Invalid or missing value for field '" + path(m) + "'.";
    }
    return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, detail);
  }

  @ExceptionHandler(MethodArgumentTypeMismatchException.class)
  ProblemDetail badParameter(MethodArgumentTypeMismatchException e) {
    return ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "Invalid value '"
            + e.getValue()
            + "' for parameter '"
            + e.getName()
            + "'"
            + allowed(e.getRequiredType())
            + ".");
  }

  @ExceptionHandler(DataIntegrityViolationException.class)
  ProblemDetail integrity(DataIntegrityViolationException e) {
    return ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "The request conflicts with existing data (duplicate or invalid reference).");
  }

  @ExceptionHandler(IllegalArgumentException.class)
  ProblemDetail badRequest(IllegalArgumentException e) {
    return ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, e.getMessage());
  }

  @ExceptionHandler(MissingRequestHeaderException.class)
  ProblemDetail missingHeader(MissingRequestHeaderException e) {
    return ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST, "Missing required header " + e.getHeaderName() + ".");
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  ProblemDetail invalid(MethodArgumentNotValidException e) {
    String fields =
        e.getBindingResult().getFieldErrors().stream()
            .map(f -> snakeCase(f.getField()) + " " + f.getDefaultMessage())
            .collect(Collectors.joining("; "));
    return ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST, "Invalid request: " + fields + ".");
  }

  /** Field names as the client sent them: the API uses snake_case JSON. */
  static String snakeCase(String javaField) {
    return javaField.replaceAll("([a-z0-9])([A-Z])", "$1_$2").toLowerCase(Locale.ROOT);
  }

  private static String path(JsonMappingException e) {
    return e.getPath().stream()
        .map(r -> r.getFieldName() != null ? r.getFieldName() : "[" + r.getIndex() + "]")
        .collect(Collectors.joining("."))
        .replace(".[", "[");
  }

  private static String allowed(Class<?> type) {
    if (type == null || !type.isEnum()) {
      return "";
    }
    return "; allowed values: "
        + Arrays.stream(type.getEnumConstants())
            .map(Object::toString)
            .collect(Collectors.joining(", "));
  }
}
