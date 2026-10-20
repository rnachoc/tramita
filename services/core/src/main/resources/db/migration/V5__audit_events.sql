-- Append-only audit trail of every state change.
CREATE TABLE audit_events (
    event_id    BIGSERIAL     PRIMARY KEY,
    claim_id    VARCHAR(24),
    occurred_at TIMESTAMPTZ   NOT NULL,
    actor       VARCHAR(100)  NOT NULL,
    actor_role  VARCHAR(16)   NOT NULL,
    event_type  VARCHAR(40)   NOT NULL,
    details     JSONB         NOT NULL
);

CREATE INDEX audit_events_claim_idx ON audit_events (claim_id, event_id);

-- The audit trail is append-only: updates and deletes are rejected by the database itself.
CREATE FUNCTION audit_events_are_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_no_update_or_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_are_immutable();
