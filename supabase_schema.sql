-- ============================================================
-- Healthcare MCP Server - Supabase Database Schema
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/_/sql/new
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. DOCTORS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    email TEXT UNIQUE,
    phone TEXT,
    qualifications TEXT[],
    years_experience INTEGER,
    bio TEXT,
    image_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for specialty lookups
CREATE INDEX IF NOT EXISTS idx_doctors_specialty ON doctors(specialty);
CREATE INDEX IF NOT EXISTS idx_doctors_active ON doctors(is_active);

-- ============================================================
-- 2. DOCTOR SCHEDULES TABLE (Weekly Recurring)
-- ============================================================
CREATE TABLE IF NOT EXISTS doctor_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id TEXT REFERENCES doctors(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Monday, 6=Sunday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doctor_id, day_of_week)
);

-- Index for schedule lookups
CREATE INDEX IF NOT EXISTS idx_schedules_doctor ON doctor_schedules(doctor_id);
CREATE INDEX IF NOT EXISTS idx_schedules_day ON doctor_schedules(day_of_week);

-- ============================================================
-- 3. DOCTOR AVAILABILITY OVERRIDES (Vacations, Extra Slots)
-- ============================================================
CREATE TABLE IF NOT EXISTS doctor_availability (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id TEXT REFERENCES doctors(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    is_available BOOLEAN DEFAULT TRUE,
    reason TEXT, -- e.g., "On vacation", "Extra clinic hours"
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doctor_id, date)
);

-- Index for availability lookups
CREATE INDEX IF NOT EXISTS idx_availability_doctor ON doctor_availability(doctor_id);
CREATE INDEX IF NOT EXISTS idx_availability_date ON doctor_availability(date);

-- ============================================================
-- 4. APPOINTMENTS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    confirmation_number TEXT UNIQUE NOT NULL,
    patient_id TEXT NOT NULL,
    doctor_id TEXT REFERENCES doctors(id) ON DELETE SET NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    specialty TEXT NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'completed', 'cancelled', 'no_show')),
    notes TEXT,
    booked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for appointment queries
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_datetime ON appointments(appointment_date, appointment_time);

-- ============================================================
-- ROW LEVEL SECURITY POLICIES
-- ============================================================

-- Enable RLS on all tables
ALTER TABLE doctors ENABLE ROW LEVEL SECURITY;
ALTER TABLE doctor_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE doctor_availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read access to doctors and schedules
CREATE POLICY "Allow public read doctors" ON doctors
    FOR SELECT USING (true);

CREATE POLICY "Allow public read schedules" ON doctor_schedules
    FOR SELECT USING (true);

CREATE POLICY "Allow public read availability" ON doctor_availability
    FOR SELECT USING (true);

-- Allow public to create appointments (with service role key in backend)
CREATE POLICY "Allow public insert appointments" ON appointments
    FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public select appointments" ON appointments
    FOR SELECT USING (true);

CREATE POLICY "Allow public update appointments" ON appointments
    FOR UPDATE USING (true);

-- ============================================================
-- TRIGGER: Update updated_at timestamp
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_doctors_updated_at ON doctors;
CREATE TRIGGER update_doctors_updated_at
    BEFORE UPDATE ON doctors
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_appointments_updated_at ON appointments;
CREATE TRIGGER update_appointments_updated_at
    BEFORE UPDATE ON appointments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 5. RAG: KNOWLEDGE BASE (pgvector)
-- Run: CREATE EXTENSION vector; in Supabase FIRST
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source ON knowledge_chunks(source);
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

-- Similarity search function used by the RAG retriever
CREATE OR REPLACE FUNCTION match_knowledge_chunks(
    query_embedding vector(1024),
    match_threshold float DEFAULT 0.6,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    source TEXT,
    content TEXT,
    metadata JSONB,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        kc.id,
        kc.source,
        kc.content,
        kc.metadata,
        1 - (kc.embedding <=> query_embedding) AS similarity
    FROM knowledge_chunks kc
    WHERE 1 - (kc.embedding <=> query_embedding) > match_threshold
    ORDER BY kc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read knowledge" ON knowledge_chunks FOR SELECT USING (true);
CREATE POLICY "Allow service insert knowledge" ON knowledge_chunks FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow service delete knowledge" ON knowledge_chunks FOR DELETE USING (true);

-- ============================================================
-- 6. WORKFLOWS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    trigger_type TEXT NOT NULL,
    trigger_config JSONB DEFAULT '{}',
    conditions JSONB DEFAULT '[]',
    actions JSONB DEFAULT '[]',
    delay_hours INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    is_agentic BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflows_trigger ON workflows(trigger_type);
CREATE INDEX IF NOT EXISTS idx_workflows_active ON workflows(is_active);

ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all workflows" ON workflows USING (true) WITH CHECK (true);

DROP TRIGGER IF EXISTS update_workflows_updated_at ON workflows;
CREATE TRIGGER update_workflows_updated_at
    BEFORE UPDATE ON workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 7. WORKFLOW RUNS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID REFERENCES workflows(id) ON DELETE CASCADE,
    trigger_data JSONB DEFAULT '{}',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    actions_taken JSONB DEFAULT '[]',
    scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_runs_workflow ON workflow_runs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_scheduled ON workflow_runs(scheduled_for);

ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all workflow_runs" ON workflow_runs USING (true) WITH CHECK (true);

-- ============================================================
-- 8. NOTIFICATIONS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id TEXT NOT NULL,
    workflow_run_id UUID REFERENCES workflow_runs(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT DEFAULT 'info' CHECK (type IN ('info', 'reminder', 'warning', 'urgent', 'doctor_alert')),
    is_read BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_patient ON notifications(patient_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all notifications" ON notifications USING (true) WITH CHECK (true);