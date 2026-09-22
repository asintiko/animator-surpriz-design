ALTER TABLE customer_accounts ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customer_accounts ADD COLUMN blocked_until TEXT;
ALTER TABLE customer_accounts ADD COLUMN block_reason TEXT NOT NULL DEFAULT '';
