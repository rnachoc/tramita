package dev.tramita.core.payment;

import dev.tramita.core.audit.AuditService;
import dev.tramita.core.claim.Claim;
import dev.tramita.core.domain.ClaimStatus;
import dev.tramita.core.web.ConflictException;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * Executes indemnity payments. Idempotent: a claim is paid at most once, enforced both here and by
 * a unique constraint in the database, so retries and concurrent requests cannot pay twice.
 */
@Service
public class PaymentService {

  private final PaymentRepository payments;
  private final AuditService audit;
  private final Clock clock;

  public PaymentService(PaymentRepository payments, AuditService audit, Clock clock) {
    this.payments = payments;
    this.audit = audit;
    this.clock = clock;
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public Payment execute(Claim claim, BigDecimal amount, Payment.Trigger trigger, String key) {
    if (amount.signum() <= 0) {
      throw new IllegalArgumentException("payment amount must be positive, got " + amount);
    }
    Optional<Payment> existing = payments.findByClaimClaimId(claim.getClaimId());
    if (existing.isPresent()) {
      if (existing.get().getAmount().compareTo(amount) != 0) {
        throw new ConflictException(
            "Claim " + claim.getClaimId() + " was already paid " + existing.get().getAmount());
      }
      return existing.get();
    }
    Instant now = Instant.now(clock);
    String iban = claim.getPolicy().getHolder().maskedIban();
    Payment payment = payments.save(new Payment(claim, key, amount, iban, trigger, now));
    claim.moveTo(ClaimStatus.PAID, now);
    audit.record(
        claim.getClaimId(),
        "PAYMENT_EXECUTED",
        Map.of(
            "payment_id",
            payment.getPaymentId().toString(),
            "amount",
            amount,
            "triggered_by",
            trigger.name(),
            "iban",
            iban));
    return payment;
  }

  @Transactional(readOnly = true)
  public Optional<Payment> forClaim(String claimId) {
    return payments.findByClaimClaimId(claimId);
  }
}
