-- ============================================================
-- IAM ADDITIONS — run this in Supabase SQL Editor
-- Adds: users table, treatment_status to appointments
-- ============================================================

-- 1. users table (auth identities)
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username      TEXT UNIQUE NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'doctor', 'patient')),
    linked_id     TEXT,        -- doctor_id (e.g. doc_001) or patient_id (e.g. PAT001)
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role     ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_linked   ON users(linked_id);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on users" ON users USING (true) WITH CHECK (true);

-- 2. Add treatment_status to appointments (if not already present)
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS treatment_status TEXT DEFAULT 'scheduled'
    CHECK (treatment_status IN ('scheduled','waiting','in_treatment','completed','no_show'));

-- 3. Seed one admin user (password: admin123)
-- Password hash for "admin123" generated with bcrypt
-- You can change the password via the app after first login
-- Seed users (change passwords via the app after first login)
-- admin / admin123
INSERT INTO users (username, email, password_hash, role, linked_id)
VALUES ('admin', 'admin@healthcare.com',
        '$2b$12$6RLNSekeHdHHEMIwjJ/bBO1IEFKqt0jp2eGkMWxNE/Jt4ckExTG8u', 'admin', NULL)
ON CONFLICT (username) DO NOTHING;

-- doctor_sarah / doctor123  (linked to doc_001 — Dr. Sarah Johnson)
INSERT INTO users (username, email, password_hash, role, linked_id)
VALUES ('doctor_sarah', 'sarah.j@healthcare.com',
        '$2b$12$zfL1uoHmaaZBoe63hPesN.05lkVgN/tFHyIaTKwM2WOez9SUyFNW6', 'doctor', 'doc_001')
ON CONFLICT (username) DO NOTHING;

-- patient_test / patient123  (linked to patient_id TEST001)
INSERT INTO users (username, email, password_hash, role, linked_id)
VALUES ('patient_test', 'test@patient.com',
        '$2b$12$GmaMigzjiM5n9EIQFbFNqe3nY4GjmAzqGZKWtnkzrtI4S8e8Cnej2', 'patient', 'TEST001')
ON CONFLICT (username) DO NOTHING;
