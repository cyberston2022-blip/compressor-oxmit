-- Migration 014: Unlimited Dynamic Mandatory Channels
CREATE TABLE IF NOT EXISTS force_sub_channels (
    channel_id BIGINT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    invite_link TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    required_for_tier VARCHAR(32) DEFAULT 'all',
    priority INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_force_sub_active ON force_sub_channels (is_active, priority DESC);
