# Configuration

Learn how to configure the admin panel (powered by [CRUDAdmin](https://github.com/benavlabs/crudadmin)) using the FastAPI boilerplate's built-in environment variable system. The admin panel is fully integrated with your application's configuration and requires no additional setup files or complex initialization.

> **About CRUDAdmin**: For complete configuration options and advanced features, see the [CRUDAdmin documentation](https://benavlabs.github.io/crudadmin/).

## Environment-Based Configuration

The FastAPI boilerplate handles all admin panel configuration through environment variables defined in your `.env` file. This approach provides consistent configuration across development, staging, and production environments.

```bash
# Basic admin panel configuration in .env
CRUD_ADMIN_ENABLED=true
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="SecurePassword123!"
CRUD_ADMIN_MOUNT_PATH="/admin"
```

The configuration system automatically:

- Validates all environment variables at startup
- Provides sensible defaults for optional settings
- Adapts security settings based on your environment (local/staging/production)
- Integrates with your application's existing security and database systems

## Core Configuration Settings

### Enable/Disable Admin Panel

Control whether the admin panel is available:

```bash
# Enable admin panel (default: true)
CRUD_ADMIN_ENABLED=true

# Disable admin panel completely
CRUD_ADMIN_ENABLED=false
```

When disabled, the admin interface is not mounted and consumes no resources.

### Admin Access Credentials

Configure the initial admin user that's created automatically:

```bash
# Required: Admin user credentials
ADMIN_USERNAME="your-admin-username"        # Admin login username
ADMIN_PASSWORD="YourSecurePassword123!"     # Admin login password

# Optional: Additional admin user details (uses existing settings)
ADMIN_NAME="Administrator"                  # Display name (from FirstUserSettings)
ADMIN_EMAIL="admin@yourcompany.com"         # Admin email (from FirstUserSettings)
```

**How this works:**

- The admin user is created automatically when the application starts
- Only created if no admin users exist (safe for restarts)
- Uses your application's existing password hashing system
- Credentials are validated according to CRUDAdmin requirements

### Interface Configuration

Customize where and how the admin panel appears:

```bash
# Admin panel URL path (default: "/admin")
CRUD_ADMIN_MOUNT_PATH="/admin"              # Access at http://localhost:8000/admin
CRUD_ADMIN_MOUNT_PATH="/management"         # Access at http://localhost:8000/management
CRUD_ADMIN_MOUNT_PATH="/internal"           # Access at http://localhost:8000/internal
```

The admin panel is mounted as a sub-application at your specified path.

## Session Management Configuration

Control how admin users stay logged in and how sessions are managed.

### Basic Session Settings

```bash
# Session limits and timeouts
CRUD_ADMIN_MAX_SESSIONS=10                  # Max concurrent sessions per user
CRUD_ADMIN_SESSION_TIMEOUT=1440             # Session timeout in minutes (24 hours)

# Cookie security
SESSION_SECURE_COOKIES=true                 # Require HTTPS for cookies (production)
```

**Session behavior:**

- Each admin login creates a new session
- Sessions expire after the timeout period of inactivity
- When max sessions are exceeded, oldest sessions are removed
- Session cookies are HTTP-only and secure (when HTTPS is enabled)

### Memory Sessions (Development)

For local development, sessions are stored in memory by default:

```bash
# Development configuration
ENVIRONMENT="local"                         # Enables memory sessions
CRUD_ADMIN_REDIS_ENABLED=false             # Explicitly disable Redis (default)
```

**Memory session characteristics:**

- Fast performance with no external dependencies
- Sessions lost when application restarts
- Suitable for single-developer environments
- Not suitable for load-balanced deployments

### Redis Sessions (Production)

For production deployments, enable Redis session storage:

```bash
# Enable Redis sessions
CRUD_ADMIN_REDIS_ENABLED=true

# Redis connection settings
CRUD_ADMIN_REDIS_HOST="localhost"          # Redis server hostname
CRUD_ADMIN_REDIS_PORT=6379                 # Redis server port
CRUD_ADMIN_REDIS_DB=0                      # Redis database number
CRUD_ADMIN_REDIS_PASSWORD="secure-pass"    # Redis authentication
CRUD_ADMIN_REDIS_SSL=false                 # Enable SSL/TLS connection
```

**Redis session benefits:**

- Sessions persist across application restarts
- Supports multiple application instances (load balancing)
- Configurable expiration and cleanup
- Production-ready scalability

**Redis URL construction:**

The boilerplate automatically constructs the Redis URL from your environment variables:

```python
# Automatic URL generation in src/app/admin/initialize.py
redis_url = f"redis{'s' if settings.CRUD_ADMIN_REDIS_SSL else ''}://"
if settings.CRUD_ADMIN_REDIS_PASSWORD:
    redis_url += f":{settings.CRUD_ADMIN_REDIS_PASSWORD}@"
redis_url += f"{settings.CRUD_ADMIN_REDIS_HOST}:{settings.CRUD_ADMIN_REDIS_PORT}/{settings.CRUD_ADMIN_REDIS_DB}"
```

## Security Configuration

The admin panel automatically adapts its security settings based on your deployment environment.

### Environment-Based Security

```bash
# Environment setting affects security behavior
ENVIRONMENT="local"                         # Development mode
ENVIRONMENT="staging"                       # Staging mode  
ENVIRONMENT="production"                    # Production mode with enhanced security
```

**Security changes by environment:**

| Setting | Local | Staging | Production |
|---------|-------|---------|------------|
| **HTTPS Enforcement** | Disabled | Optional | Enabled |
| **Secure Cookies** | Optional | Recommended | Required |
| **Session Tracking** | Optional | Recommended | Enabled |
| **Event Logging** | Optional | Recommended | Enabled |

### Audit and Tracking

Enable comprehensive logging for compliance and security monitoring:

```bash
# Event and session tracking
CRUD_ADMIN_TRACK_EVENTS=true               # Log all admin actions
CRUD_ADMIN_TRACK_SESSIONS=true             # Track session lifecycle

# Available in admin interface
# - View all admin actions with timestamps
# - Monitor active sessions
# - Track user activity patterns
```

### Access Restrictions

The boilerplate supports IP and network-based access restrictions (configured in code):

```python
# In src/app/admin/initialize.py - customize as needed
admin = CRUDAdmin(
    # ... other settings ...
    allowed_ips=settings.CRUD_ADMIN_ALLOWED_IPS_LIST,      # Specific IP addresses
    allowed_networks=settings.CRUD_ADMIN_ALLOWED_NETWORKS_LIST,  # CIDR network ranges
)
```

To implement IP restrictions, extend the `CRUDAdminSettings` class in `src/app/core/config.py`.

## Integration with Application Settings

The admin panel leverages your existing application configuration for seamless integration.

### Shared Security Settings

```bash
# Uses your application's main secret key
SECRET_KEY="your-application-secret-key"    # Shared with admin panel

# Inherits database settings
POSTGRES_USER="dbuser"                      # Admin uses same database
POSTGRES_PASSWORD="dbpass"
POSTGRES_SERVER="localhost"
POSTGRES_DB="yourapp"
```

### Automatic Configuration Loading

The admin panel automatically inherits settings from your application:

```python
# In src/app/admin/initialize.py
admin = CRUDAdmin(
    session=async_get_db,                   # Your app's database session
    SECRET_KEY=settings.SECRET_KEY.get_secret_value(),  # Your app's secret key
    enforce_https=settings.ENVIRONMENT == EnvironmentOption.PRODUCTION,
    # ... other settings from your app configuration
)
```

## Deployment Examples

### Development Environment

Perfect for local development with minimal setup:

```bash
# .env.development
ENVIRONMENT="local"
CRUD_ADMIN_ENABLED=true
ADMIN_USERNAME="dev-admin"
ADMIN_PASSWORD="dev123"
CRUD_ADMIN_MOUNT_PATH="/admin"

# Memory sessions - no external dependencies
CRUD_ADMIN_REDIS_ENABLED=false

# Optional tracking for testing
CRUD_ADMIN_TRACK_EVENTS=false
CRUD_ADMIN_TRACK_SESSIONS=false
```

### Staging Environment

Staging environment with Redis but relaxed security:

```bash
# .env.staging
ENVIRONMENT="staging"
CRUD_ADMIN_ENABLED=true
ADMIN_USERNAME="staging-admin"
ADMIN_PASSWORD="StagingPassword123!"

# Redis sessions for testing production behavior
CRUD_ADMIN_REDIS_ENABLED=true
CRUD_ADMIN_REDIS_HOST="staging-redis.example.com"
CRUD_ADMIN_REDIS_PASSWORD="staging-redis-pass"

# Enable tracking for testing
CRUD_ADMIN_TRACK_EVENTS=true
CRUD_ADMIN_TRACK_SESSIONS=true
SESSION_SECURE_COOKIES=true
```

### Production Environment

Production-ready configuration with full security:

```bash
# .env.production
ENVIRONMENT="production"
CRUD_ADMIN_ENABLED=true
ADMIN_USERNAME="prod-admin"
ADMIN_PASSWORD="VerySecureProductionPassword123!"

# Redis sessions for scalability
CRUD_ADMIN_REDIS_ENABLED=true
CRUD_ADMIN_REDIS_HOST="redis.internal.company.com"
CRUD_ADMIN_REDIS_PORT=6379
CRUD_ADMIN_REDIS_PASSWORD="ultra-secure-redis-password"
CRUD_ADMIN_REDIS_SSL=true

# Full security and tracking
SESSION_SECURE_COOKIES=true
CRUD_ADMIN_TRACK_EVENTS=true
CRUD_ADMIN_TRACK_SESSIONS=true
CRUD_ADMIN_MAX_SESSIONS=5
CRUD_ADMIN_SESSION_TIMEOUT=480              # 8 hours for security
```

### Docker Deployment

Configure for containerized deployments:

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: .
    environment:
      - ENVIRONMENT=production
      - ADMIN_USERNAME=${ADMIN_USERNAME}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      
      # Redis connection
      - CRUD_ADMIN_REDIS_ENABLED=true
      - CRUD_ADMIN_REDIS_HOST=redis
      - CRUD_ADMIN_REDIS_PORT=6379
      - CRUD_ADMIN_REDIS_PASSWORD=${REDIS_PASSWORD}
      
    depends_on:
      - redis
      - postgres

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
```

```bash
# .env file for Docker
ADMIN_USERNAME="docker-admin"
ADMIN_PASSWORD="DockerSecurePassword123!"
REDIS_PASSWORD="docker-redis-password"
```

## Configuration Validation

The boilerplate automatically validates your configuration at startup and provides helpful error messages.

### Common Configuration Issues

**Missing Required Variables:**
```bash
# Error: Admin credentials not provided
# Solution: Add to .env
ADMIN_USERNAME="your-admin"
ADMIN_PASSWORD="your-password"
```

**Invalid Redis Configuration:**
```bash
# Error: Redis connection failed
# Check Redis server and credentials
CRUD_ADMIN_REDIS_HOST="correct-redis-host"
CRUD_ADMIN_REDIS_PASSWORD="correct-password"
```

**Security Warnings:**
```bash
# Warning: Weak admin password
# Use stronger password with mixed case, numbers, symbols
ADMIN_PASSWORD="StrongerPassword123!"
```

## What's Next

With your admin panel configured, you're ready to:

1. **[Adding Models](adding-models.md)** - Register your application models with the admin interface
2. **[User Management](user-management.md)** - Manage admin users and implement security best practices

The configuration system provides flexibility for any deployment scenario while maintaining consistency across environments. 