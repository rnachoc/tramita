package dev.tramita.core.review;

import dev.tramita.core.domain.Decision;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

/**
 * A claims handler's decision. {@code decision} and {@code amount} are required when correcting; a
 * comment is required when correcting or rejecting.
 */
public record ReviewRequest(
    @NotBlank @Size(max = 100) String reviewer,
    @NotNull ReviewAction action,
    Decision decision,
    @DecimalMin("0.00") BigDecimal amount,
    @Size(max = 5_000) String comment) {}
