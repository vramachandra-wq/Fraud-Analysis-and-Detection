CREATE SCHEMA IF NOT EXISTS curated;
DROP TABLE IF EXISTS curated.users CASCADE;

CREATE TABLE curated.users (
    user_key                SERIAL       PRIMARY KEY,
    username                VARCHAR(50)  UNIQUE NOT NULL,
    password_plain          VARCHAR(255) NOT NULL, -- Storing plain text for POC
    custom_role_name        VARCHAR(100) NOT NULL, 
    
    -- Granular Feature Flags (Dashboard Permissions)
    has_access_transactions BOOLEAN      DEFAULT FALSE, 
    has_access_vip_hub      BOOLEAN      DEFAULT FALSE,
    has_access_chatbot      BOOLEAN      DEFAULT FALSE,
    
    is_active               BOOLEAN      DEFAULT TRUE,
    created_at              TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- Seed your master system admin profile with plain text credentials
INSERT INTO curated.users (
    username, password_plain, custom_role_name, 
    has_access_transactions, has_access_vip_hub, has_access_chatbot
) VALUES (
    'admin', 'admin', 'System Administrator', 
    TRUE, TRUE, TRUE
) ON CONFLICT (username) DO NOTHING;