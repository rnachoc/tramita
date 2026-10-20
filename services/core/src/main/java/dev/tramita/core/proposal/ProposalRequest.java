package dev.tramita.core.proposal;

import dev.tramita.core.domain.Decision;
import dev.tramita.core.domain.FraudSignalType;
import dev.tramita.core.rules.FraudSignal;
import dev.tramita.core.rules.Proposal;
import dev.tramita.core.rules.SignalSource;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/** A proposal as submitted by the agent service. */
public record ProposalRequest(
    @NotNull Decision decision,
    @DecimalMin("0.00") BigDecimal eligibleAmount,
    @DecimalMin("0.00") BigDecimal proposedAmount,
    String exclusionCode,
    @NotNull List<@NotBlank String> citations,
    @NotNull @Valid List<Signal> fraudSignals,
    @NotBlank @Size(max = 20_000) String rationale,
    Map<String, Object> modelMetadata) {

  /** A fraud signal proposed by the fraud agent. */
  public record Signal(@NotNull FraudSignalType type, String evidence, double confidence) {}

  public Proposal toProposal() {
    List<FraudSignal> signals =
        fraudSignals.stream()
            .map(s -> new FraudSignal(s.type(), s.evidence(), s.confidence(), SignalSource.MODEL))
            .toList();
    return new Proposal(
        decision, eligibleAmount, proposedAmount, exclusionCode, citations, signals);
  }
}
