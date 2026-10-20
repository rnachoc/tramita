-- Payments executed to policyholders. One payment per claim, enforced by the database.
CREATE TABLE payments (
    payment_id       UUID          PRIMARY KEY,
    claim_id         VARCHAR(24)   NOT NULL UNIQUE REFERENCES claims (claim_id),
    idempotency_key  VARCHAR(100)  NOT NULL UNIQUE,
    amount           NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    iban_masked      VARCHAR(40)   NOT NULL,
    reference        VARCHAR(40)   NOT NULL,
    triggered_by     VARCHAR(16)   NOT NULL CHECK (triggered_by IN ('RULES', 'REVIEW')),
    executed_at      TIMESTAMPTZ   NOT NULL
);
