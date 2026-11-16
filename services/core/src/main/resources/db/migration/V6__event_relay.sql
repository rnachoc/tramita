-- How far the event relay has published the audit trail, which doubles as the transactional
-- outbox: every state change writes its audit event in the same transaction (ADR 0014).
CREATE TABLE event_relay (
    relay         VARCHAR(40)  PRIMARY KEY,
    last_event_id BIGINT       NOT NULL,
    updated_at    TIMESTAMPTZ  NOT NULL
);

INSERT INTO event_relay (relay, last_event_id, updated_at) VALUES ('kafka', 0, now());
