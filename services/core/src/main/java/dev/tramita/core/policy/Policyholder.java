package dev.tramita.core.policy;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDate;

/** A customer of the insurer. Contains personal data: never logged, never sent to a model. */
@Entity
@Table(name = "policyholders")
public class Policyholder {

  @Id
  @Column(name = "holder_id")
  private String holderId;

  private String fullName;
  private String nif;
  private LocalDate birthDate;
  private String email;
  private String phone;
  private String street;
  private String postalCode;
  private String city;
  private String province;
  private String iban;

  protected Policyholder() {}

  public Policyholder(
      String holderId,
      String fullName,
      String nif,
      LocalDate birthDate,
      String email,
      String phone,
      String street,
      String postalCode,
      String city,
      String province,
      String iban) {
    this.holderId = holderId;
    this.fullName = fullName;
    this.nif = nif;
    this.birthDate = birthDate;
    this.email = email;
    this.phone = phone;
    this.street = street;
    this.postalCode = postalCode;
    this.city = city;
    this.province = province;
    this.iban = iban;
  }

  public String getHolderId() {
    return holderId;
  }

  public String getFullName() {
    return fullName;
  }

  public String getNif() {
    return nif;
  }

  public String getIban() {
    return iban;
  }

  public String getCity() {
    return city;
  }

  public String getProvince() {
    return province;
  }

  /** IBAN with everything but the country code and the last four digits hidden. */
  public String maskedIban() {
    String compact = iban.replace(" ", "");
    return compact.substring(0, 2)
        + "** **** **** **** **** "
        + compact.substring(compact.length() - 4);
  }
}
