package dev.tramita.core.policy;

import dev.tramita.core.audit.AuditService;
import dev.tramita.core.catalog.Catalog;
import dev.tramita.core.web.NotFoundException;
import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PolicyService {

  private final PolicyholderRepository holders;
  private final PolicyRepository policies;
  private final Catalog catalog;
  private final AuditService audit;

  public PolicyService(
      PolicyholderRepository holders,
      PolicyRepository policies,
      Catalog catalog,
      AuditService audit) {
    this.holders = holders;
    this.policies = policies;
    this.catalog = catalog;
    this.audit = audit;
  }

  /** Upserts policyholders and policies. Re-importing the same data is a no-op. */
  @Transactional
  public PolicyImport.Result importAll(PolicyImport.Request request) {
    Map<String, Policyholder> byId = new HashMap<>();
    for (PolicyImport.Holder h : request.policyholders()) {
      PolicyImport.Address a = h.address();
      Policyholder holder =
          new Policyholder(
              h.holderId(),
              h.fullName(),
              h.nif(),
              h.birthDate(),
              h.email(),
              h.phone(),
              a.street(),
              a.postalCode(),
              a.city(),
              a.province(),
              h.iban());
      byId.put(h.holderId(), holders.save(holder));
    }
    for (PolicyImport.PolicyItem p : request.policies()) {
      Catalog.Product product =
          catalog
              .product(p.productCode())
              .orElseThrow(
                  () -> new IllegalArgumentException("Unknown product code " + p.productCode()));
      if (product.line() != p.line()) {
        throw new IllegalArgumentException(
            "Policy "
                + p.policyNumber()
                + " has line "
                + p.line()
                + " but product "
                + p.productCode()
                + " is "
                + product.line());
      }
      Policyholder holder = byId.get(p.holderId());
      if (holder == null) {
        holder =
            holders
                .findById(p.holderId())
                .orElseThrow(() -> new NotFoundException("Unknown policyholder " + p.holderId()));
      }
      Policy policy =
          new Policy(
              p.policyNumber(),
              holder,
              p.productCode(),
              p.line(),
              p.startDate(),
              p.endDate(),
              p.annualPremium());
      if (p.insuredAddress() != null) {
        PolicyImport.Address a = p.insuredAddress();
        policy.withInsuredAddress(a.street() + ", " + a.postalCode() + " " + a.city());
      }
      if (p.vehicle() != null) {
        PolicyImport.Vehicle v = p.vehicle();
        policy.withVehicle(v.plate(), v.make(), v.model(), v.year(), p.insuredValue());
      }
      policies.save(policy);
    }
    audit.record(
        null,
        "POLICIES_IMPORTED",
        Map.of(
            "policyholders",
            request.policyholders().size(),
            "policies",
            request.policies().size()));
    return new PolicyImport.Result(request.policyholders().size(), request.policies().size());
  }

  @Transactional(readOnly = true)
  public Policy get(String policyNumber) {
    return policies
        .findById(policyNumber)
        .orElseThrow(() -> new NotFoundException("Unknown policy " + policyNumber));
  }
}
