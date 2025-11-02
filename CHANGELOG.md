# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2025-11-03

### 🎉 Sprint 4a: ETL Automation & Data Quality

Major milestone! Complete automation of ETL pipeline with idempotency, intelligent date extraction, and scheduled imports.

### Added
- **Automated Daily Import Scheduler** (#82)
  - Task Scheduler integration (Mon-Fri 12:10 MSK)
  - Inbox directory monitoring (`data/inbox/`)
  - Automatic file archiving to `data/archive/YYYY-MM-DD/`
  - Comprehensive structured logging to `logs/import.log`
  - Error handling (failed files stay in inbox)
  - Statistics tracking (success/error counts)
  - Job orchestration script: `jobs/ingest_dw_price.py`
  - Windows setup script: `scripts/setup_scheduler.ps1`

- **Idempotent Import with SHA256 Fingerprinting** (#80)
  - File fingerprinting prevents duplicate imports
  - New table `dw_files` for import tracking
  - SHA256 hash calculation for all imported files
  - Fast duplicate detection without full file read
  - Complete import audit trail

- **Automatic price_date Extraction** (#81)
  - Intelligent parsing from filename patterns
  - Excel header scanning (rows 2-8)
  - Multiple date format support (DD.MM.YYYY, YYYY-MM-DD, DD/MM/YYYY)
  - Fallback to current date if not found
  - Supports both Russian and international date formats

- **Enhanced ETL Logging** (#62)
  - Structured JSON logging for ETL operations
  - Request ID correlation across operations
  - Performance metrics (duration, rows processed)
  - File-specific context (name, hash, size)
  - Integration with existing logging infrastructure

### Changed
- Updated `scripts/load_csv.py` with idempotency checks
- Enhanced file handling with automatic archiving
- Improved error reporting and recovery
- Extended database schema with `dw_files` table

### Infrastructure
- Task Scheduler configuration for Windows
- Cron-ready design for Linux/macOS
- Automated directory structure creation
- Log rotation support

### Documentation
- Comprehensive "Automated ETL Import" section in README
- Setup instructions for Task Scheduler
- Troubleshooting guide for common issues
- Architecture diagrams for automation flow

---

## [0.4.1] - 2025-10-31

### Added
- **Structured JSON Logging** (#53)
  - JSON-formatted logs for all API operations
  - Unique Request ID for request tracing
  - Performance metrics (duration_ms, response_size_bytes)
  - Client context (IP, User-Agent, method, path)
  - Integration-ready for Datadog, ELK, Splunk
  - Configurable log levels via LOG_LEVEL env var

### Changed
- Migrated from plain text to JSON logging format
- Enhanced error logging with structured context
- Improved observability for production deployments

---

## [0.4.0] - 2025-10-30

### Added
- **Rate Limiting with Flask-Limiter** (#51)
  - DDoS protection for all endpoints
  - Configurable limits (100/1000 requests/hour)
  - Rate limit headers (X-RateLimit-*)
  - Redis support for distributed limiting
  - Environment-based configuration

### Fixed
- **SQL Injection Vulnerability** (#49)
  - Removed SQL comments from query strings
  - Enhanced input sanitization
  - Parameterized query improvements

### Changed
- Updated OpenAPI documentation with rate limits
- Enhanced security headers
- Improved error messages

---

## [0.3.0] - 2025-10-28

### Added
- **OpenAPI 3.0 Specification** (#47)
  - Interactive Swagger UI at `/docs`
  - Complete API documentation
  - Request/response examples
  - Authentication documentation

- **Docker Health Checks** (#46, #42)
  - Liveness probe: `/live`
  - Readiness probe: `/ready`
  - Database connection validation
  - Automatic service restart on failure

- **CORS Support** (#41)
  - Configurable origin whitelist
  - Environment-based configuration
  - Pre-flight request handling

### Documentation
- Updated README to v0.3.0
- Production deployment guide
- Troubleshooting section
- Architecture diagrams

---

## [0.2.0] - 2025-10-15

### Added
- Bitemporal data model implementation
- Price history tracking
- Stock history tracking
- Advanced search with pg_trgm

### Changed
- Database schema optimization
- ETL pipeline improvements
- Enhanced data validation

---

## [0.1.0] - 2025-10-01

### Added
- Initial Flask API implementation
- PostgreSQL database setup
- Basic product catalog
- CSV/Excel import functionality
- Docker Compose configuration
- Basic health checks

---

## Version History

- **v0.5.0** - Sprint 4a: ETL Automation & Data Quality (Current)
- **v0.4.1** - Sprint 3.1: Structured JSON Logging
- **v0.4.0** - Sprint 3: Security & Rate Limiting
- **v0.3.0** - Sprint 2: Production Readiness
- **v0.2.0** - Sprint 1: Core Functionality
- **v0.1.0** - Initial Release

---

## Links

- [GitHub Repository](https://github.com/glinozem/wine-assistant)
- [Issue Tracker](https://github.com/glinozem/wine-assistant/issues)
- [Discussions](https://github.com/glinozem/wine-assistant/discussions)
