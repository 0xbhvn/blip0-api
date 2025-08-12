# Admin Panel

The FastAPI boilerplate comes with a pre-configured web-based admin interface powered by [CRUDAdmin](https://github.com/benavlabs/crudadmin) that provides instant database management capabilities. Learn how to access, configure, and customize the admin panel for your development and production needs.

> **Powered by CRUDAdmin**: This admin panel is built with [CRUDAdmin](https://github.com/benavlabs/crudadmin), a modern admin interface generator for FastAPI applications.
> 
> - **📚 CRUDAdmin Documentation**: [benavlabs.github.io/crudadmin](https://benavlabs.github.io/crudadmin/)
> - **💻 CRUDAdmin GitHub**: [github.com/benavlabs/crudadmin](https://github.com/benavlabs/crudadmin)

## What You'll Learn

- **[Configuration](configuration.md)** - Environment variables and deployment settings
- **[Adding Models](adding-models.md)** - Register your new models with the admin interface
- **[User Management](user-management.md)** - Manage admin users and security

## Admin Panel Overview

Your FastAPI boilerplate includes a fully configured admin interface that's ready to use out of the box. The admin panel automatically provides web-based management for your database models without requiring any additional setup.

**What's Already Configured:**

- Complete admin interface mounted at `/admin`
- User, Tier, and Post models already registered
- Automatic form generation and validation
- Session management with configurable backends
- Security features and access controls

**Accessing the Admin Panel:**

1. Start your application: `uv run fastapi dev`
2. Navigate to: `http://localhost:8000/admin`
3. Login with default credentials (configured via environment variables)

## Pre-Registered Models

The boilerplate comes with three models already set up in the admin interface:

### User Management
```python
# Already registered in your admin
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update"},
    password_transformer=password_transformer,  # Automatic password hashing
)
```

**Features:**

- Create and manage application users
- Automatic password hashing with bcrypt
- User profile management (name, username, email)
- Tier assignment for subscription management

### Tier Management
```python
# Subscription tiers for your application
admin.add_view(
    model=Tier, 
    create_schema=TierCreate, 
    update_schema=TierUpdate, 
    allowed_actions={"view", "create", "update", "delete"}
)
```

**Features:**

- Manage subscription tiers and pricing
- Configure rate limits per tier
- Full CRUD operations available

### Content Management
```python
# Post/content management
admin.add_view(
    model=Post,
    create_schema=PostCreateAdmin,  # Special admin schema
    update_schema=PostUpdate,
    allowed_actions={"view", "create", "update", "delete"}
)
```

**Features:**

- Manage user-generated content
- Handle media URLs and content validation
- Associate posts with users

## Quick Start

### 1. Set Up Admin Credentials

Configure your admin login in your `.env` file:

```bash
# Admin Panel Access
ADMIN_USERNAME="your-admin-username"
ADMIN_PASSWORD="YourSecurePassword123!"

# Basic Configuration
CRUD_ADMIN_ENABLED=true
CRUD_ADMIN_MOUNT_PATH="/admin"
```

### 2. Start the Application

```bash
# Development
uv run fastapi dev

# The admin panel will be available at:
# http://localhost:8000/admin
```

### 3. Login and Explore

1. **Access**: Navigate to `/admin` in your browser
2. **Login**: Use the credentials from your environment variables
3. **Explore**: Browse the pre-configured models (Users, Tiers, Posts)

## Environment Configuration

The admin panel is configured entirely through environment variables, making it easy to adapt for different deployment environments.

### Basic Settings

```bash
# Enable/disable admin panel
CRUD_ADMIN_ENABLED=true                    # Set to false to disable completely

# Admin interface path
CRUD_ADMIN_MOUNT_PATH="/admin"             # Change the URL path

# Admin user credentials (created automatically)
ADMIN_USERNAME="admin"                     # Your admin username
ADMIN_PASSWORD="SecurePassword123!"       # Your admin password
```

### Session Management

```bash
# Session configuration
CRUD_ADMIN_MAX_SESSIONS=10                 # Max concurrent sessions per user
CRUD_ADMIN_SESSION_TIMEOUT=1440            # Session timeout (24 hours)
SESSION_SECURE_COOKIES=true                # HTTPS-only cookies
```

### Production Security

```bash
# Security settings for production
ENVIRONMENT="production"                   # Enables HTTPS enforcement
CRUD_ADMIN_TRACK_EVENTS=true              # Log admin actions
CRUD_ADMIN_TRACK_SESSIONS=true            # Track session activity
```

### Redis Session Storage

For production deployments with multiple server instances:

```bash
# Enable Redis sessions
CRUD_ADMIN_REDIS_ENABLED=true
CRUD_ADMIN_REDIS_HOST="localhost"
CRUD_ADMIN_REDIS_PORT=6379
CRUD_ADMIN_REDIS_DB=0
CRUD_ADMIN_REDIS_PASSWORD="your-redis-password"
CRUD_ADMIN_REDIS_SSL=false
```

## How It Works

The admin panel integrates seamlessly with your FastAPI application through several key components:

### Automatic Initialization

```python
# In src/app/main.py - already configured
admin = create_admin_interface()

@asynccontextmanager
async def lifespan_with_admin(app: FastAPI):
    async with default_lifespan(app):
        if admin:
            await admin.initialize()  # Sets up admin database
        yield

# Admin is mounted automatically at your configured path
if admin:
    app.mount(settings.CRUD_ADMIN_MOUNT_PATH, admin.app)
```

### Configuration Integration

```python
# In src/app/admin/initialize.py - uses your existing settings
admin = CRUDAdmin(
    session=async_get_db,                      # Your database session
    SECRET_KEY=settings.SECRET_KEY,            # Your app's secret key
    mount_path=settings.CRUD_ADMIN_MOUNT_PATH, # Configurable path
    secure_cookies=settings.SESSION_SECURE_COOKIES,
    enforce_https=settings.ENVIRONMENT == EnvironmentOption.PRODUCTION,
    # ... all configured via environment variables
)
```

### Model Registration

```python
# In src/app/admin/views.py - pre-configured models
def register_admin_views(admin: CRUDAdmin):
    # Password handling for User model
    password_transformer = PasswordTransformer(
        password_field="password",
        hashed_field="hashed_password",
        hash_function=get_password_hash,  # Uses your app's password hashing
    )
    
    # Register your models with appropriate schemas
    admin.add_view(model=User, create_schema=UserCreate, ...)
    admin.add_view(model=Tier, create_schema=TierCreate, ...)
    admin.add_view(model=Post, create_schema=PostCreateAdmin, ...)
```

## Development vs Production

### Development Setup

For local development, minimal configuration is needed:

```bash
# .env for development
CRUD_ADMIN_ENABLED=true
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="admin123"
ENVIRONMENT="local"

# Uses memory sessions (fast, no external dependencies)
CRUD_ADMIN_REDIS_ENABLED=false
```

### Production Setup

For production deployments, enable additional security features:

```bash
# .env for production
CRUD_ADMIN_ENABLED=true
ADMIN_USERNAME="production-admin"
ADMIN_PASSWORD="VerySecureProductionPassword123!"
ENVIRONMENT="production"

# Redis sessions for scalability
CRUD_ADMIN_REDIS_ENABLED=true
CRUD_ADMIN_REDIS_HOST="your-redis-host"
CRUD_ADMIN_REDIS_PASSWORD="secure-redis-password"
CRUD_ADMIN_REDIS_SSL=true

# Enhanced security
SESSION_SECURE_COOKIES=true
CRUD_ADMIN_TRACK_EVENTS=true
CRUD_ADMIN_TRACK_SESSIONS=true
```

## Getting Started Guide

### 1. **[Configuration](configuration.md)** - Environment Setup

Learn about all available environment variables and how to configure the admin panel for different deployment scenarios. Understand session backends and security settings.

Perfect for setting up development environments and preparing for production deployment.

### 2. **[Adding Models](adding-models.md)** - Extend the Admin Interface

Discover how to register your new models with the admin interface. Learn from the existing User, Tier, and Post implementations to add your own models.

Essential when you create new database models and want them managed through the admin interface.

### 3. **[User Management](user-management.md)** - Admin Security

Understand how admin authentication works, how to create additional admin users, and implement security best practices for production environments.

Critical for production deployments where multiple team members need admin access.

## What's Next

Ready to start using your admin panel? Follow this path:

1. **[Configuration](configuration.md)** - Set up your environment variables and understand deployment options
2. **[Adding Models](adding-models.md)** - Add your new models to the admin interface  
3. **[User Management](user-management.md)** - Implement secure admin authentication

The admin panel is ready to use immediately with sensible defaults, and each guide shows you how to customize it for your specific needs. 