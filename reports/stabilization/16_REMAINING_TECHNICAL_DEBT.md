# Remaining Technical Debt & Future Recommendations

1. **Phase 2 Webpanel Features:** Webpanel v2 nav displays Upcoming placeholders for Limits Editor and Archive Browser. These should be implemented in Phase 2.
2. **Containerized Test Target:** Introduce a dedicated `docker compose -f docker-compose.test.yml` for automated CI/CD pipeline runs.
3. **Off-host Backup Replication:** Configure `BACKUP_RCLONE_TARGET` with an S3 or B2 bucket to ensure off-site disaster recovery.
