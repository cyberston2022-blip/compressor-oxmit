-- SEC-1c: scrub token-bearing Local Bot API paths from persisted error text.
-- Idempotent; safe to run repeatedly. The directory component of
-- /var/lib/telegram-bot-api/<token>/... is replaced with <REDACTED>.
-- NOTE: the token contains a colon ("id:secret") — the character class must
-- only exclude '/' and whitespace so the whole segment is consumed.

UPDATE jobs
SET error_message = regexp_replace(
        error_message,
        '/var/lib/telegram-bot-api/[^/\s]+',
        '/var/lib/telegram-bot-api/<REDACTED>',
        'g')
WHERE error_message LIKE '%telegram-bot-api/%';

UPDATE deliveries
SET error = regexp_replace(
        error,
        '/var/lib/telegram-bot-api/[^/\s]+',
        '/var/lib/telegram-bot-api/<REDACTED>',
        'g')
WHERE error LIKE '%telegram-bot-api/%';
