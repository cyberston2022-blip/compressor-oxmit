-- HEVC escalation pass profile (auto-triggered when the x264 level pass
-- yields no size gain on an already-tight source).

INSERT INTO profiles(key, encore_name, title, description, version)
VALUES ('level265', 'level265', 'Smart compress HEVC',
        'HEVC escalation pass - CRF +5 over the x264 level pass', 1)
ON CONFLICT (key) DO NOTHING;
