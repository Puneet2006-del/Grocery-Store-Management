USE zerowaste;

-- ===== Accounts, ownership and per-owner rules =====

CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(150) NOT NULL UNIQUE,
  display_name VARCHAR(100) NOT NULL,
  password_salt VARCHAR(64) NOT NULL,       -- base64
  password_hash VARCHAR(128) NOT NULL,      -- PBKDF2-HMAC-SHA256, 120,000 rounds, base64
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_tokens (
  token_hash CHAR(64) PRIMARY KEY,          -- SHA-256 of the token; the token itself is never stored
  user_id BIGINT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  INDEX idx_token_user (user_id)
);

-- A shopkeeper's own rule values; any rule not listed here uses the default in business_rules
CREATE TABLE IF NOT EXISTS owner_rules (
  owner_id BIGINT NOT NULL,
  rule_key VARCHAR(50) NOT NULL,
  rule_value VARCHAR(100) NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (owner_id, rule_key),
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (rule_key) REFERENCES business_rules(rule_key)
);

-- Every shop belongs to one shopkeeper. Run this line only once.
ALTER TABLE stores
  ADD COLUMN owner_id BIGINT NULL,
  ADD CONSTRAINT fk_store_owner FOREIGN KEY (owner_id) REFERENCES users(user_id),
  ADD INDEX idx_store_owner (owner_id);
