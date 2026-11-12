-- Migration 013: Artifacts and Multi-Part Output Tracking
CREATE TABLE IF NOT EXISTS job_artifacts (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    artifact_type VARCHAR(32) NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_artifacts_job_id ON job_artifacts (job_id);
