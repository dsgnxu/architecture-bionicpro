-- Mock CRM: clients linked to Keycloak / LDAP usernames
CREATE TABLE IF NOT EXISTS clients (
    user_id     VARCHAR(64) PRIMARY KEY,
    username    VARCHAR(128) NOT NULL UNIQUE,
    full_name   VARCHAR(256) NOT NULL,
    email       VARCHAR(256),
    crm_status  VARCHAR(64) NOT NULL DEFAULT 'active',
    prosthesis_model VARCHAR(128) NOT NULL,
    registered_at DATE NOT NULL DEFAULT CURRENT_DATE
);

INSERT INTO clients (user_id, username, full_name, email, crm_status, prosthesis_model, registered_at) VALUES
    ('u-prothetic1', 'prothetic1', 'Prothetic User One', 'prothetic1@example.com', 'active', 'BionicPRO-X1', '2025-01-10'),
    ('u-prothetic2', 'prothetic2', 'Prothetic User Two', 'prothetic2@example.com', 'active', 'BionicPRO-X1', '2025-02-01'),
    ('u-prothetic3', 'prothetic3', 'Prothetic User Three', 'prothetic3@example.com', 'active', 'BionicPRO-X2', '2025-03-15'),
    ('u-john-doe', 'john.doe', 'John Doe', 'john.doe@bionicpro.local', 'active', 'BionicPRO-X1', '2025-01-20'),
    ('u-alex-johnson', 'alex.johnson', 'Alex Johnson', 'alex.johnson@bionicpro.local', 'active', 'BionicPRO-X2', '2025-04-01')
ON CONFLICT (user_id) DO NOTHING;
