-- Claims as filed, and the documents attached to them.
CREATE TABLE claims (
    claim_id        VARCHAR(24)   PRIMARY KEY,
    policy_number   VARCHAR(24)   NOT NULL REFERENCES policies (policy_number),
    claim_type      VARCHAR(24)   NOT NULL,
    incident_date   DATE          NOT NULL,
    reported_date   DATE          NOT NULL,
    location        VARCHAR(300)  NOT NULL,
    description     TEXT          NOT NULL,
    claimed_amount  NUMERIC(12, 2),
    contact_phone   VARCHAR(32),
    contact_email   VARCHAR(200),
    status          VARCHAR(24)   NOT NULL,
    created_at      TIMESTAMPTZ   NOT NULL,
    updated_at      TIMESTAMPTZ   NOT NULL,
    version         BIGINT        NOT NULL DEFAULT 0,
    CHECK (reported_date >= incident_date)
);

CREATE INDEX claims_policy_idx ON claims (policy_number, reported_date);
CREATE INDEX claims_status_idx ON claims (status, updated_at);

CREATE TABLE claim_documents (
    document_id     VARCHAR(24)   PRIMARY KEY,
    claim_id        VARCHAR(24)   NOT NULL REFERENCES claims (claim_id),
    document_type   VARCHAR(24)   NOT NULL,
    filename        VARCHAR(200)  NOT NULL,
    storage_key     VARCHAR(400),
    received_at     TIMESTAMPTZ   NOT NULL,
    -- Facts extracted by the agent service; personal data is masked before storage.
    extraction      JSONB,
    extracted_at    TIMESTAMPTZ,
    issue_date      DATE,
    issuer_tax_id   VARCHAR(16),
    document_number VARCHAR(40),
    stated_total    NUMERIC(12, 2),
    tax_rate        NUMERIC(5, 2),
    line_amounts    JSONB
);

CREATE INDEX claim_documents_claim_idx ON claim_documents (claim_id);
-- Duplicate-invoice detection looks up earlier documents by issuer and number.
CREATE INDEX claim_documents_invoice_idx ON claim_documents (issuer_tax_id, document_number);
