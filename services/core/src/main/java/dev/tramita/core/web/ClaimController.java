package dev.tramita.core.web;

import dev.tramita.core.audit.AuditService;
import dev.tramita.core.catalog.Catalog;
import dev.tramita.core.claim.Claim;
import dev.tramita.core.claim.ClaimRequests;
import dev.tramita.core.claim.ClaimService;
import dev.tramita.core.domain.ClaimStatus;
import dev.tramita.core.payment.PaymentService;
import dev.tramita.core.policy.PolicyView;
import dev.tramita.core.proposal.ProposalRepository;
import dev.tramita.core.proposal.ProposalRequest;
import dev.tramita.core.proposal.ProposalService;
import dev.tramita.core.proposal.ProposalView;
import dev.tramita.core.review.ReviewRequest;
import dev.tramita.core.review.ReviewService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * The claims API used by the agent service, the review console and analysts. Each request runs in
 * one transaction so responses can be assembled from lazily loaded associations.
 */
@RestController
@Transactional
public class ClaimController {

  private static final String IDEMPOTENCY_KEY = "Idempotency-Key";

  private final ClaimService claims;
  private final ProposalService proposalService;
  private final ProposalRepository proposals;
  private final ReviewService reviews;
  private final PaymentService payments;
  private final AuditService audit;
  private final Catalog catalog;

  public ClaimController(
      ClaimService claims,
      ProposalService proposalService,
      ProposalRepository proposals,
      ReviewService reviews,
      PaymentService payments,
      AuditService audit,
      Catalog catalog) {
    this.claims = claims;
    this.proposalService = proposalService;
    this.proposals = proposals;
    this.reviews = reviews;
    this.payments = payments;
    this.audit = audit;
    this.catalog = catalog;
  }

  @PostMapping("/api/claims")
  @ResponseStatus(HttpStatus.CREATED)
  public Views.ClaimSummary register(@Valid @RequestBody ClaimRequests.Register request) {
    return Views.ClaimSummary.of(claims.register(request));
  }

  @PostMapping("/api/claims/{claimId}/documents")
  @ResponseStatus(HttpStatus.CREATED)
  public Views.DocumentView addDocument(
      @PathVariable String claimId, @Valid @RequestBody ClaimRequests.AddDocument request) {
    return Views.DocumentView.of(claims.addDocument(claimId, request));
  }

  @PutMapping("/api/claims/{claimId}/documents/{documentId}/extraction")
  public Views.DocumentView recordExtraction(
      @PathVariable String claimId,
      @PathVariable String documentId,
      @Valid @RequestBody ClaimRequests.Extraction request) {
    return Views.DocumentView.of(claims.recordExtraction(claimId, documentId, request));
  }

  @PostMapping("/api/claims/{claimId}/proposals")
  public Views.ProposalSubmitted submitProposal(
      @PathVariable String claimId,
      @RequestHeader(IDEMPOTENCY_KEY) String idempotencyKey,
      @Valid @RequestBody ProposalRequest request) {
    ProposalService.Outcome outcome = proposalService.submit(claimId, idempotencyKey, request);
    return new Views.ProposalSubmitted(
        ProposalView.of(outcome.proposal()),
        outcome.claimStatus(),
        outcome.payment().map(Views.PaymentView::of).orElse(null));
  }

  @PostMapping("/api/claims/{claimId}/reviews")
  public Views.ReviewRecorded review(
      @PathVariable String claimId,
      @RequestHeader(IDEMPOTENCY_KEY) String idempotencyKey,
      @Valid @RequestBody ReviewRequest request) {
    ReviewService.Outcome outcome = reviews.review(claimId, idempotencyKey, request);
    return new Views.ReviewRecorded(
        Views.ReviewView.of(outcome.review()),
        outcome.claimStatus(),
        outcome.payment().map(Views.PaymentView::of).orElse(null));
  }

  @GetMapping("/api/claims")
  public List<Views.ClaimSummary> list(
      @RequestParam(defaultValue = "PENDING_REVIEW,UNDER_INVESTIGATION") List<ClaimStatus> status,
      @RequestParam(defaultValue = "100") int limit) {
    return claims.byStatus(status, limit).stream().map(Views.ClaimSummary::of).toList();
  }

  @GetMapping("/api/claims/{claimId}")
  public Views.ClaimView get(@PathVariable String claimId) {
    Claim c = claims.get(claimId);
    String productName =
        catalog.product(c.getPolicy().getProductCode()).map(Catalog.Product::name).orElse("");
    return new Views.ClaimView(
        c.getClaimId(),
        c.getStatus(),
        c.getClaimType(),
        c.getIncidentDate(),
        c.getReportedDate(),
        c.getLocation(),
        c.getDescription(),
        c.getClaimedAmount(),
        PolicyView.of(c.getPolicy(), productName),
        claims.documents(claimId).stream().map(Views.DocumentView::of).toList(),
        proposals.findByClaimClaimIdOrderByCreatedAtAsc(claimId).stream()
            .map(ProposalView::of)
            .toList(),
        reviews.forClaim(claimId).stream().map(Views.ReviewView::of).toList(),
        payments.forClaim(claimId).map(Views.PaymentView::of).orElse(null));
  }

  @GetMapping("/api/claims/{claimId}/audit")
  public List<Views.AuditView> audit(@PathVariable String claimId) {
    claims.get(claimId);
    return audit.trail(claimId).stream().map(Views.AuditView::of).toList();
  }

  @GetMapping("/api/policies/{policyNumber}/claims")
  public List<Views.ClaimSummary> policyClaims(@PathVariable String policyNumber) {
    return claims.onPolicy(policyNumber).stream().map(Views.ClaimSummary::of).toList();
  }
}
