-- Proposals made by the agents, the rules evaluation of each, and human reviews.
CREATE TABLE proposals (
    proposal_id      UUID          PRIMARY KEY,
    claim_id         VARCHAR(24)   NOT NULL REFERENCES claims (claim_id),
    idempotency_key  VARCHAR(100)  NOT NULL UNIQUE,
    created_at       TIMESTAMPTZ   NOT NULL,
    proposed_decision VARCHAR(16)  NOT NULL,
    eligible_amount  NUMERIC(12, 2),
    proposed_amount  NUMERIC(12, 2),
    exclusion_code   VARCHAR(40),
    citations        JSONB         NOT NULL,
    fraud_signals    JSONB         NOT NULL,
    rationale        TEXT          NOT NULL,
    model_metadata   JSONB,
    -- Outcome of the rules engine; it overrides the proposal when they disagree.
    decision         VARCHAR(16)   NOT NULL,
    payable_amount   NUMERIC(12, 2) NOT NULL,
    routing          VARCHAR(24)   NOT NULL,
    fraud_score      NUMERIC(6, 4) NOT NULL,
    evaluation       JSONB         NOT NULL
);

CREATE INDEX proposals_claim_idx ON proposals (claim_id, created_at);

CREATE TABLE reviews (
    review_id        UUID          PRIMARY KEY,
    claim_id         VARCHAR(24)   NOT NULL REFERENCES claims (claim_id),
    proposal_id      UUID          NOT NULL REFERENCES proposals (proposal_id),
    idempotency_key  VARCHAR(100)  NOT NULL UNIQUE,
    reviewer         VARCHAR(100)  NOT NULL,
    action           VARCHAR(16)   NOT NULL CHECK (action IN ('APPROVE', 'CORRECT', 'REJECT')),
    decision         VARCHAR(16)   NOT NULL,
    amount           NUMERIC(12, 2) NOT NULL,
    comment          TEXT,
    created_at       TIMESTAMPTZ   NOT NULL
);

CREATE INDEX reviews_claim_idx ON reviews (claim_id, created_at);
