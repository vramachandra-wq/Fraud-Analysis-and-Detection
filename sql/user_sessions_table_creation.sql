-- 1. Create the base session tracking table
CREATE TABLE IF NOT EXISTS curated.user_sessions (
    session_id       BIGSERIAL PRIMARY KEY,
    user_key         INT NOT NULL,
    username         VARCHAR(50) NOT NULL,
    login_time       TIMESTAMP NOT NULL DEFAULT NOW(),
    logout_time      TIMESTAMP,
    last_heartbeat   TIMESTAMP NOT NULL DEFAULT NOW(),
    session_status   VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    session_token    VARCHAR(64) UNIQUE,
    
    -- Foreign key constraint linking to your master users table
    CONSTRAINT fk_user_sessions_user_key 
        FOREIGN KEY (user_key) 
        REFERENCES curated.users(user_key) 
        ON DELETE CASCADE
);

-- 2. Add structural check guardrails to maintain status validity
ALTER TABLE curated.user_sessions 
    ADD CONSTRAINT chk_session_status 
    CHECK (session_status IN ('ACTIVE', 'LOGOUT', 'CRASHED'));

-- 3. High-performance indexes for monitoring and dashboard lookups
CREATE INDEX idx_user_sessions_user_key 
    ON curated.user_sessions(user_key);

CREATE INDEX idx_user_sessions_token 
    ON curated.user_sessions(session_token) 
    WHERE session_status = 'ACTIVE';

CREATE INDEX idx_user_sessions_heartbeat 
    ON curated.user_sessions(session_status, last_heartbeat DESC);