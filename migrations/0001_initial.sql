CREATE TABLE endpoints (
    id TEXT PRIMARY KEY,
    public_token_hash TEXT NOT NULL UNIQUE,
    manage_token_hash TEXT NOT NULL UNIQUE,
    destination_email TEXT NOT NULL,
    origin TEXT NOT NULL,
    email_verified_at TEXT,
    verification_token_hash TEXT UNIQUE,
    verification_expires_at TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    is_permanent INTEGER NOT NULL DEFAULT 0,
    permanent_at TEXT
);

CREATE TABLE submissions (
    id TEXT PRIMARY KEY,
    endpoint_id TEXT NOT NULL REFERENCES endpoints(id),
    received_at TEXT NOT NULL,
    sender_name TEXT,
    sender_email TEXT,
    subject TEXT,
    message TEXT,
    extra_fields TEXT NOT NULL DEFAULT '{}',
    forwarded_at TEXT,
    forward_status TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX idx_submissions_endpoint_id ON submissions(endpoint_id);
CREATE INDEX idx_endpoints_verification_token ON endpoints(verification_token_hash);
