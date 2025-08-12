# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Running the Application

```bash
# Using Docker Compose (recommended)
docker compose up

# Running locally with uvicorn
uv run uvicorn src.app.main:app --reload

# Running background worker
uv run arq src.app.core.worker.settings.WorkerSettings
```

### Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_user_unit.py

# Run with verbose output
uv run pytest -v
```

### Code Quality

```bash
# Run linter
uv run ruff check src/

# Run linter with auto-fix
uv run ruff check --fix src/

# Run type checker
uv run mypy src/
```

### Database Migrations

```bash
# Generate migration
uv run alembic revision --autogenerate

# Apply migrations
uv run alembic upgrade head
```

### Initial Setup Scripts

```bash
# Create first superuser
uv run python -m src.scripts.create_first_superuser

# Create first tier
uv run python -m src.scripts.create_first_tier
```

## Project Context: Blip0 Monitoring Platform

### Overview

This repository (`blip0-api`) is the Python/FastAPI configuration management layer for the Blip0 blockchain monitoring platform. It works in conjunction with the Rust-based `oz-multi-tenant` monitor runtime to provide a complete multi-tenant monitoring solution.

### Architecture Split Strategy

Based on the analysis in `oz-multi-tenant/docs/ARCHITECTURE_SPLIT_ANALYSIS.md`, the system follows a split architecture:

- **Rust Monitor Runtime** (`oz-multi-tenant`): Handles high-performance block processing, real-time monitoring, and filter execution
- **Python API** (this repository): Manages configuration, tenant management, CRUD operations, and administrative interfaces

### Phase 2 Development Goals

According to the migration checklist, this API layer is responsible for:

1. **Platform-Managed Resources** (Blip0 team controls):
   - Network configurations (blockchain networks)
   - Filter scripts (monitoring templates)
   - System-wide settings

2. **User-Managed Resources** (Tenants control):
   - Monitor configurations
   - Trigger settings (Email, Webhook, Discord, Slack)
   - Alert preferences

3. **Communication Layer**:
   - Write-through caching to Redis for sub-millisecond access by Rust monitor
   - Denormalized data structures optimized for read performance
   - 30-second cache refresh intervals for configuration updates

### Key Design Decisions

- **Redis-Only Approach**: No HTTP fallback; Rust reads exclusively from Redis
- **Performance Targets**: <1ms configuration access, <50ms API response times
- **Multi-Tenancy**: Row-level security with tenant isolation at all layers
- **Operational Focus**: Prioritize reliability over architectural elegance

## High-Level Architecture

### Application Structure

The application follows a layered architecture pattern with clear separation of concerns:

1. **API Layer** (`src/app/api/`): FastAPI routers handling HTTP requests and responses. All API endpoints are versioned under `/api/v1/`.

2. **Business Logic Layer**:
   - **CRUD Operations** (`src/app/crud/`): Database operations using FastCRUD for standardized CRUD patterns
   - **Schemas** (`src/app/schemas/`): Pydantic models for request/response validation and serialization

3. **Data Layer**:
   - **Models** (`src/app/models/`): SQLAlchemy ORM models defining database tables
   - **Database** (`src/app/core/db/`): Database connection management and base configurations

4. **Core Services** (`src/app/core/`):
   - **Authentication**: JWT-based auth with access and refresh tokens
   - **Caching**: Redis-based caching with decorator pattern for endpoints
   - **Rate Limiting**: Tier-based rate limiting using Redis
   - **Background Jobs**: ARQ worker for async task processing
   - **Security**: Password hashing, token management, and blacklisting

### Key Architectural Patterns

1. **Async/Await Throughout**: The entire application uses async patterns for optimal performance with `asyncpg` for database and `aioredis` for cache/queue operations.

2. **Dependency Injection**: FastAPI's dependency injection is used extensively for database sessions, authentication, and rate limiting.

3. **Repository Pattern**: CRUD operations are abstracted through FastCRUD, providing a consistent interface for database operations.

4. **Multi-Tenancy Ready**: The architecture supports multi-tenant isolation through:
   - Row-Level Security (RLS) preparation in database models
   - Tenant-aware authentication and authorization
   - Isolated rate limiting per tier/tenant

5. **Cache-First Strategy**: Redis caching is integrated at multiple levels:
   - Endpoint response caching with automatic invalidation
   - Client-side cache headers
   - Session storage for admin panel

6. **Queue-Based Background Processing**: ARQ worker handles long-running tasks asynchronously, with database session management built into worker context.

### Service Dependencies

- **PostgreSQL**: Primary database with async support via asyncpg
- **Redis**: Used for caching, rate limiting, queue management, and session storage
- **Docker**: Containerization for all services with docker-compose orchestration

### Authentication Flow

1. User logs in via `/api/v1/login` → receives access token (30min) and refresh token cookie (7 days)
2. Access protected endpoints with `Authorization: Bearer <token>` header
3. Refresh access token via `/api/v1/refresh` using the refresh token cookie
4. Logout via `/api/v1/logout` which blacklists the token

### Admin Panel

The application includes a CRUDAdmin interface at `/admin` with:

- Full CRUD operations for all models
- Session management with optional Redis backend
- Event tracking and audit logging capabilities
- Configurable security settings via environment variables

### Environment Configuration

All configuration is managed through environment variables in `src/.env`. The `Settings` class in `src/app/core/config.py` aggregates all settings using Pydantic Settings management, allowing easy opt-in/opt-out of services by modifying class inheritance.

## Redis Schema Design for Blip0

Based on the Phase 2 architecture, the following Redis schema will be implemented:

### Platform-Managed Keys (Shared Across Tenants)

```bash
platform:networks:{network_slug}     → Network configuration JSON
platform:filters:{script_name}       → Filter script templates JSON
```

### Tenant-Specific Keys

```bash
tenant:{tenant_id}:monitors:active   → List of active monitor IDs
tenant:{tenant_id}:monitor:{id}      → Denormalized monitor with triggers
```

### Data Flow

1. User creates/updates configuration via Python API
2. API writes to **PostgreSQL** (primary persistent storage, source of truth)
3. API immediately writes-through to **Redis** (cache layer, denormalized for performance)
4. Rust monitor reads from Redis every 30 seconds (never directly from PostgreSQL)
5. Rust processes blocks using cached configurations

### Storage Architecture

- **PostgreSQL**:
  - Primary persistent storage for all configurations
  - Source of truth for all data
  - Handles complex queries, relationships, and transactions
  - Stores audit logs, execution history, and all tenant data
  
- **Redis**:
  - Cache layer for ultra-fast read access by Rust monitor
  - Denormalized data optimized for the monitor's access patterns
  - Automatically synchronized with PostgreSQL via write-through caching
  - Not a persistent storage - can be rebuilt from PostgreSQL at any time

## Development Priorities for Phase 2

### Immediate Tasks (Week 1-2)

1. **Monitor CRUD API**: Implement endpoints for monitor management
2. **Trigger Configuration**: Support Email and Webhook triggers initially
3. **Redis Integration**: Implement write-through caching with denormalization
4. **Tenant Isolation**: Ensure proper multi-tenant data separation

### Platform Admin Features

1. **Network Management**: CRUD for blockchain network configurations
2. **Filter Script Templates**: Manage reusable monitoring templates
3. **Tenant Management**: Create and manage tenant accounts

### User-Facing Features

1. **Monitor Dashboard**: View and manage active monitors
2. **Alert Configuration**: Set up Email/Webhook notifications
3. **Execution History**: Track monitor execution and alerts

### Future Enhancements

1. **Discord/Slack Integration**: Additional trigger types
2. **Advanced Filtering**: Complex filter composition
3. **Analytics Dashboard**: Monitor performance metrics
4. **API Rate Limiting**: Per-tenant usage controls
