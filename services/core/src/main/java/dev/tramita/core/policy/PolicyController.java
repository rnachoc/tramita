package dev.tramita.core.policy;

import dev.tramita.core.catalog.Catalog;
import jakarta.validation.Valid;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Transactional
public class PolicyController {

  private final PolicyService service;
  private final Catalog catalog;

  public PolicyController(PolicyService service, Catalog catalog) {
    this.service = service;
    this.catalog = catalog;
  }

  @PostMapping("/api/import/policies")
  public PolicyImport.Result importPolicies(@Valid @RequestBody PolicyImport.Request request) {
    return service.importAll(request);
  }

  @GetMapping("/api/policies/{policyNumber}")
  public PolicyView get(@PathVariable String policyNumber) {
    Policy policy = service.get(policyNumber);
    String name = catalog.product(policy.getProductCode()).map(Catalog.Product::name).orElse("");
    return PolicyView.of(policy, name);
  }
}
