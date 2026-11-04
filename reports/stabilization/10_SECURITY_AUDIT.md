# Security Audit

- **Authentication:** Admin panel v2 uses strong tokens, rate-limited login, signed httpOnly cookies, and strict CSRF validation.
- **Sensitive Data Redaction:** All file paths containing bot tokens are automatically scrubbed via `media.redact()` before logging or storing in error columns.
- **Subprocess Execution:** All FFmpeg and FFprobe calls use parameterized argument lists (`shlex` compatible), avoiding `shell=True` command injection.
- **File System Boundary:** Local Bot API volume is mounted read-only where possible, preventing unauthorized file mutations.
