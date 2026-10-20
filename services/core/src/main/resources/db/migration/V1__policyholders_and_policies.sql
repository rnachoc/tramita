-- Policyholders and the policies they hold.
CREATE TABLE policyholders (
    holder_id     VARCHAR(16)  PRIMARY KEY,
    full_name     VARCHAR(200) NOT NULL,
    nif           VARCHAR(16)  NOT NULL UNIQUE,
    birth_date    DATE         NOT NULL,
    email         VARCHAR(200) NOT NULL,
    phone         VARCHAR(32)  NOT NULL,
    street        VARCHAR(200) NOT NULL,
    postal_code   VARCHAR(10)  NOT NULL,
    city          VARCHAR(100) NOT NULL,
    province      VARCHAR(100) NOT NULL,
    iban          VARCHAR(40)  NOT NULL
);

CREATE TABLE policies (
    policy_number   VARCHAR(24)   PRIMARY KEY,
    holder_id       VARCHAR(16)   NOT NULL REFERENCES policyholders (holder_id),
    product_code    VARCHAR(8)    NOT NULL,
    line            VARCHAR(8)    NOT NULL CHECK (line IN ('HOME', 'AUTO')),
    start_date      DATE          NOT NULL,
    end_date        DATE          NOT NULL,
    annual_premium  NUMERIC(10, 2) NOT NULL,
    insured_value   NUMERIC(12, 2),
    insured_address VARCHAR(300),
    vehicle_plate   VARCHAR(16),
    vehicle_make    VARCHAR(40),
    vehicle_model   VARCHAR(40),
    vehicle_year    INTEGER,
    CHECK (end_date >= start_date)
);

CREATE INDEX policies_holder_idx ON policies (holder_id);
