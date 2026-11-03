-- Smart compression profile (user level 1-20 -> CRF 18-28 via profileParams).

INSERT INTO profiles(key, encore_name, title, description, version)
VALUES ('level', 'level', 'Smart compress',
        'CRF quality scale 1-20, content-adaptive size reduction', 1)
ON CONFLICT (key) DO NOTHING;
