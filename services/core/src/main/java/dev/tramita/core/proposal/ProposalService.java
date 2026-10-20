package dev.tramita.core.proposal;

import dev.tramita.core.audit.AuditService;
import dev.tramita.core.claim.Claim;
import dev.tramita.core.claim.ClaimFactsAssembler;
import dev.tramita.core.claim.ClaimService;
import dev.tramita.core.domain.ClaimStatus;
import dev.tramita.core.domain.Decision;
import dev.tramita.core.payment.Payment;
import dev.tramita.core.payment.PaymentService;
import dev.tramita.core.rules.ClaimFacts;
import dev.tramita.core.rules.Evaluation;
import dev.tramita.core.rules.RulesEngine;
import dev.tramita.core.rules.Violation;
import dev.tramita.core.web.ConflictException;
import java.time.Clock;
import java.time.Instant;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Receives proposals from the agents, has the rules engine check them and applies the outcome.
 *
 * <p>Only when the rules route a proposal to AUTO is it executed here; anything else waits for a
 * human. Submissions are idempotent on the {@code Idempotency-Key} the agent sends.
 */
@Service
public class ProposalService {

  /** Statuses in which the agents may (re)assess a claim. */
  private static final Set<ClaimStatus> OPEN_FOR_PROPOSALS =
      EnumSet.of(ClaimStatus.RECEIVED, ClaimStatus.WAITING_DOCUMENTS);

  private final ProposalRepository proposals;
  private final ClaimService claims;
  private final ClaimFactsAssembler facts;
  private final RulesEngine rules;
  private final PaymentService payments;
  private final AuditService audit;
  private final Clock clock;

  public ProposalService(
      ProposalRepository proposals,
      ClaimService claims,
      ClaimFactsAssembler facts,
      RulesEngine rules,
      PaymentService payments,
      AuditService audit,
      Clock clock) {
    this.proposals = proposals;
    this.claims = claims;
    this.facts = facts;
    this.rules = rules;
    this.payments = payments;
    this.audit = audit;
    this.clock = clock;
  }

  /** The outcome of a submission: the checked proposal, the new claim status and any payment. */
  public record Outcome(
      ProposalRecord proposal, ClaimStatus claimStatus, Optional<Payment> payment) {}

  @Transactional
  public Outcome submit(String claimId, String idempotencyKey, ProposalRequest request) {
    Optional<ProposalRecord> replay = proposals.findByIdempotencyKey(idempotencyKey);
    if (replay.isPresent()) {
      ProposalRecord p = replay.get();
      if (!p.getClaim().getClaimId().equals(claimId)) {
        throw new ConflictException(
            "Idempotency-Key already used for claim " + p.getClaim().getClaimId());
      }
      return new Outcome(p, p.getClaim().getStatus(), payments.forClaim(claimId));
    }

    Claim claim = claims.get(claimId);
    if (!OPEN_FOR_PROPOSALS.contains(claim.getStatus())) {
      throw new ConflictException(
          "Claim "
              + claimId
              + " is "
              + claim.getStatus()
              + "; proposals are accepted only while it is "
              + OPEN_FOR_PROPOSALS);
    }
    ClaimFacts claimFacts = facts.assemble(claim);
    Evaluation evaluation =
        rules.evaluate(claim.getPolicy().facts(), claimFacts, request.toProposal());

    Instant now = Instant.now(clock);
    ProposalRecord record =
        proposals.save(
            new ProposalRecord(
                claim,
                idempotencyKey,
                now,
                request.decision(),
                request.eligibleAmount(),
                request.proposedAmount(),
                request.exclusionCode(),
                request.citations(),
                request.toProposal().fraudSignals(),
                request.rationale(),
                request.modelMetadata(),
                evaluation));
    claim.moveTo(nextStatus(evaluation), now);
    audit.record(claimId, "PROPOSAL_EVALUATED", details(record, evaluation));

    Optional<Payment> payment = Optional.empty();
    if (evaluation.canExecuteAutomatically()
        && evaluation.decision() == Decision.APPROVE
        && evaluation.payableAmount().signum() > 0) {
      payment =
          Optional.of(
              payments.execute(
                  claim,
                  evaluation.payableAmount(),
                  Payment.Trigger.RULES,
                  "rules:" + record.getProposalId()));
    }
    return new Outcome(record, claim.getStatus(), payment);
  }

  private static ClaimStatus nextStatus(Evaluation e) {
    return switch (e.routing()) {
      case FRAUD_INVESTIGATION -> ClaimStatus.UNDER_INVESTIGATION;
      case HUMAN_REVIEW -> ClaimStatus.PENDING_REVIEW;
      case AUTO ->
          switch (e.decision()) {
            case APPROVE -> ClaimStatus.APPROVED;
            case REQUEST_INFO -> ClaimStatus.WAITING_DOCUMENTS;
            // The rules never route a rejection to AUTO; treat it as needing review if they did.
            case REJECT -> ClaimStatus.PENDING_REVIEW;
          };
    };
  }

  private static Map<String, Object> details(ProposalRecord record, Evaluation e) {
    Map<String, Object> details = new HashMap<>();
    details.put("proposal_id", record.getProposalId().toString());
    details.put("proposed_decision", record.getProposedDecision().name());
    details.put("decision", e.decision().name());
    details.put("payable_amount", e.payableAmount());
    details.put("routing", e.routing().name());
    details.put("fraud_score", e.fraudScore());
    details.put("violations", e.violations().stream().map(Violation::code).toList());
    return details;
  }
}
