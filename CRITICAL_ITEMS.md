# Critical Items Remaining

This document outlines the remaining work needed for production readiness, organized by priority.

---

## Priority 1: Critical (Must Fix Before Production)

### Security

1. **API Key Authentication System** - Currently only admin secret exists
   - Implement API key table with hashed keys
   - Add rate limiting per API key
   - Add usage tracking and billing hooks
   - Location: `backend/app/models/api_key.py` (model exists, endpoints needed)

2. **JWT Token Authentication** - For user sessions
   - Add user model with password hashing
   - Implement login/logout endpoints
   - Add token refresh mechanism
   - Location: New `backend/app/routers/auth.py`

3. **Input Sanitization for Search** - Prevent injection attacks
   - Sanitize PostgreSQL tsquery input more thoroughly
   - Add SQL injection protection for dynamic filters
   - Location: `backend/app/services/postgres_search.py:208`

4. **Secrets Management** - Remove hardcoded defaults
   - Change default `ADMIN_SECRET` from "change-me-in-production"
   - Add validation that secrets are set in production mode
   - Location: `backend/app/config.py`

### Data Integrity

5. **Database Backup Strategy** - No backup system in place
   - Add pg_dump scheduled task
   - Configure Qdrant snapshots
   - Add backup verification
   - Location: New `backend/app/tasks/backup.py`

6. **Qdrant Vector Consistency** - Vectors can get out of sync with PostgreSQL
   - Add reconciliation job to detect orphaned vectors
   - Add cleanup task for deleted episodes
   - Location: `backend/app/tasks/maintenance.py`

---

## Priority 2: High (Should Fix Soon)

### Testing

7. **Integration Tests** - Current tests are minimal
   - Add end-to-end transcription pipeline tests
   - Add search accuracy tests with fixtures
   - Add WebSocket connection tests
   - Location: `backend/tests/integration/`

8. **Load Testing** - No performance benchmarks
   - Add locust or k6 load tests
   - Benchmark search latency under load
   - Test connection pool behavior
   - Location: New `backend/tests/load/`

### Monitoring

9. **Structured Logging** - Logs aren't easily queryable
   - Add JSON log formatting for production
   - Add correlation IDs across services
   - Integrate with log aggregation (ELK, Datadog)
   - Location: `backend/app/main.py:15-20`

10. **Metrics Collection** - No Prometheus/StatsD metrics
    - Add request latency histograms
    - Add search result count metrics
    - Add transcription cost metrics
    - Location: New `backend/app/middleware/metrics.py`

11. **Alerting** - No alerting system
    - Add Sentry error tracking (config exists, not fully integrated)
    - Add PagerDuty/Slack alerts for failures
    - Add budget alerts for transcription costs
    - Location: `backend/app/config.py:88` (SENTRY_DSN)

### Performance

12. **Search Result Pagination** - Currently returns all results at once
    - Add cursor-based pagination for large result sets
    - Add total count estimation
    - Location: `backend/app/services/search.py`

13. **Embedding Batch Processing** - Single-threaded embedding generation
    - Add parallel embedding generation
    - Optimize batch sizes for OpenAI API
    - Location: `backend/app/services/embedding.py`

14. **Qdrant Sharding** - Single collection won't scale
    - Implement collection sharding by channel or date
    - Add shard routing logic
    - Location: `backend/app/services/vector_store.py`

---

## Priority 3: Medium (Nice to Have)

### Features

15. **Search Analytics** - No tracking of search queries
    - Log popular queries
    - Track zero-result queries
    - Add search suggestions based on history
    - Location: New `backend/app/services/analytics.py`

16. **Transcript Editing** - No way to correct transcription errors
    - Add utterance edit endpoint
    - Re-embed on edit
    - Track edit history
    - Location: `backend/app/routers/episodes.py`

17. **Export Functionality** - No way to export transcripts
    - Add SRT/VTT subtitle export
    - Add JSON/CSV transcript export
    - Add bulk export for channels
    - Location: New `backend/app/routers/export.py`

18. **Multi-Language Support** - Currently English only
    - Add language detection
    - Configure Whisper for multi-language
    - Add language filter to search
    - Location: `backend/app/services/transcription/`

### Frontend

19. **Mobile Responsiveness** - Admin pages not mobile-optimized
    - Fix batch management on mobile
    - Add touch-friendly controls
    - Location: `frontend/app/admin/`

20. **Keyboard Shortcuts** - No keyboard navigation
    - Add search shortcuts (/, Ctrl+K)
    - Add navigation shortcuts
    - Location: `frontend/components/`

21. **Dark Mode** - No theme support
    - Add dark mode toggle
    - Persist preference
    - Location: `frontend/app/layout.tsx`

22. **Offline Support** - No PWA capabilities
    - Add service worker
    - Cache recent searches
    - Location: `frontend/public/`

### DevOps

23. **CI/CD Pipeline** - No automated deployment
    - Add GitHub Actions for testing
    - Add automated Docker builds
    - Add staging environment
    - Location: New `.github/workflows/`

24. **Infrastructure as Code** - Manual deployment
    - Add Terraform/Pulumi configs
    - Add Kubernetes manifests (optional)
    - Location: New `deploy/terraform/`

25. **Database Migrations in CI** - Manual migration running
    - Add migration check in CI
    - Add rollback procedures
    - Location: `.github/workflows/`

---

## Priority 4: Low (Future Enhancements)

### Advanced Features

26. **Semantic Caching** - Cache by query similarity
    - Use embedding similarity for cache hits
    - Reduce embedding API calls
    - Location: `backend/app/services/cache.py`

27. **Query Expansion** - Improve search recall
    - Add synonym expansion
    - Add query rewriting with LLM
    - Location: `backend/app/services/search.py`

28. **Personalization** - No user preferences
    - Track user search history
    - Add bookmarks/favorites
    - Personalized recommendations
    - Location: New user model and services

29. **Podcast RSS Import** - Currently YouTube only
    - Add RSS feed parsing
    - Support audio file upload
    - Location: New `backend/app/services/rss.py`

30. **Collaborative Features** - Single-user system
    - Add team/organization support
    - Add shared channels
    - Add role-based access
    - Location: New models and auth system

---

## Quick Wins (Can Do Today)

These are small fixes that provide immediate value:

- [ ] Add `robots.txt` to frontend
- [ ] Add `sitemap.xml` generation for public channels
- [ ] Add OpenGraph meta tags for sharing
- [ ] Add favicon and app icons
- [ ] Add loading skeletons to frontend
- [ ] Add error boundaries to React components
- [ ] Add `CHANGELOG.md` for version tracking
- [ ] Add `.env.example` with all variables documented
- [ ] Add Docker health checks for all services
- [ ] Add graceful shutdown handlers

---

## Estimated Effort

| Priority | Items | Estimated Days |
|----------|-------|----------------|
| Critical | 6 | 5-7 days |
| High | 8 | 8-12 days |
| Medium | 10 | 10-15 days |
| Low | 5 | 5-10 days |
| Quick Wins | 10 | 1-2 days |

**Total**: ~30-45 days of focused development for full production readiness.

---

## Recommended Order

1. **Week 1**: Critical security items (1-4), backup strategy (5)
2. **Week 2**: Vector consistency (6), integration tests (7), structured logging (9)
3. **Week 3**: Metrics (10), alerting (11), pagination (12)
4. **Week 4**: CI/CD (23), load testing (8), remaining high priority
5. **Ongoing**: Medium and low priority as time permits
