package dev.tramita.core.policy;

import dev.tramita.core.domain.Line;
import dev.tramita.core.rules.PolicyFacts;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;

/** An insurance contract for one product. */
@Entity
@Table(name = "policies")
public class Policy {

  @Id private String policyNumber;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "holder_id")
  private Policyholder holder;

  private String productCode;

  @Enumerated(EnumType.STRING)
  private Line line;

  private LocalDate startDate;
  private LocalDate endDate;
  private BigDecimal annualPremium;
  private BigDecimal insuredValue;
  private String insuredAddress;
  private String vehiclePlate;
  private String vehicleMake;
  private String vehicleModel;
  private Integer vehicleYear;

  protected Policy() {}

  public Policy(
      String policyNumber,
      Policyholder holder,
      String productCode,
      Line line,
      LocalDate startDate,
      LocalDate endDate,
      BigDecimal annualPremium) {
    this.policyNumber = policyNumber;
    this.holder = holder;
    this.productCode = productCode;
    this.line = line;
    this.startDate = startDate;
    this.endDate = endDate;
    this.annualPremium = annualPremium;
  }

  public Policy withInsuredAddress(String address) {
    this.insuredAddress = address;
    return this;
  }

  public Policy withVehicle(
      String plate, String make, String model, Integer year, BigDecimal value) {
    this.vehiclePlate = plate;
    this.vehicleMake = make;
    this.vehicleModel = model;
    this.vehicleYear = year;
    this.insuredValue = value;
    return this;
  }

  public PolicyFacts facts() {
    return new PolicyFacts(policyNumber, productCode, startDate, endDate, insuredValue);
  }

  public String getPolicyNumber() {
    return policyNumber;
  }

  public Policyholder getHolder() {
    return holder;
  }

  public String getProductCode() {
    return productCode;
  }

  public Line getLine() {
    return line;
  }

  public LocalDate getStartDate() {
    return startDate;
  }

  public LocalDate getEndDate() {
    return endDate;
  }

  public BigDecimal getAnnualPremium() {
    return annualPremium;
  }

  public BigDecimal getInsuredValue() {
    return insuredValue;
  }

  public String getInsuredAddress() {
    return insuredAddress;
  }

  public String getVehiclePlate() {
    return vehiclePlate;
  }

  public String getVehicleMake() {
    return vehicleMake;
  }

  public String getVehicleModel() {
    return vehicleModel;
  }

  public Integer getVehicleYear() {
    return vehicleYear;
  }
}
