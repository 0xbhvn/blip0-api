# User Management

Learn how to manage admin users in your FastAPI boilerplate's admin panel. The boilerplate automatically creates admin users from environment variables and provides a separate authentication system (powered by [CRUDAdmin](https://github.com/benavlabs/crudadmin)) from your application users.

> **CRUDAdmin Authentication**: For advanced authentication features and session management, see the [CRUDAdmin documentation](https://benavlabs.github.io/crudadmin/).

## Initial Admin Setup

### Configure Admin Credentials

Set your admin credentials in your `.env` file:

```bash
# Required admin credentials
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="SecurePassword123!"

# Optional details
ADMIN_NAME="Administrator"
ADMIN_EMAIL="admin@yourcompany.com"
```

### Access the Admin Panel

Start your application and access the admin panel:

```bash
# Start application
uv run fastapi dev

# Visit: http://localhost:8000/admin
# Login with your ADMIN_USERNAME and ADMIN_PASSWORD
```

The boilerplate automatically creates the initial admin user from your environment variables when the application starts.

## Managing Admin Users

### Creating Additional Admin Users

Once logged in, you can create more admin users through the admin interface:

1. Navigate to the admin users section in the admin panel
2. Click "Create" or "Add New"
3. Fill in the required fields:
   - Username (must be unique)
   - Password (will be hashed automatically)
   - Email (optional)

### Admin User Requirements

- **Username**: 3-50 characters, letters/numbers/underscores/hyphens
- **Password**: Minimum 8 characters with mixed case, numbers, and symbols
- **Email**: Valid email format (optional)

### Updating and Removing Users

- **Update**: Find the user in the admin panel and click "Edit"
- **Remove**: Click "Delete" (ensure you have alternative admin access first)

## Security Configuration

### Environment-Specific Settings

Configure different security levels for each environment:

```bash
# Development
ADMIN_USERNAME="dev-admin"
ADMIN_PASSWORD="DevPass123!"
ENVIRONMENT="local"

# Production
ADMIN_USERNAME="prod-admin"
ADMIN_PASSWORD="VerySecurePassword123!"
ENVIRONMENT="production"
CRUD_ADMIN_TRACK_EVENTS=true
CRUD_ADMIN_TRACK_SESSIONS=true
SESSION_SECURE_COOKIES=true
```

### Session Management

Control admin sessions with these settings:

```bash
# Session limits and timeouts
CRUD_ADMIN_MAX_SESSIONS=10          # Max concurrent sessions per user
CRUD_ADMIN_SESSION_TIMEOUT=1440     # Timeout in minutes (24 hours)
SESSION_SECURE_COOKIES=true         # HTTPS-only cookies
```

### Enable Tracking

Monitor admin activity by enabling event tracking:

```bash
# Track admin actions and sessions
CRUD_ADMIN_TRACK_EVENTS=true        # Log all admin actions  
CRUD_ADMIN_TRACK_SESSIONS=true      # Track session lifecycle
```

## Production Deployment

### Secure Credential Management

For production, use Docker secrets or Kubernetes secrets instead of plain text:

```yaml
# docker-compose.yml
services:
  web:
    secrets:
      - admin_username
      - admin_password
    environment:
      - ADMIN_USERNAME_FILE=/run/secrets/admin_username
      - ADMIN_PASSWORD_FILE=/run/secrets/admin_password

secrets:
  admin_username:
    file: ./secrets/admin_username.txt
  admin_password:
    file: ./secrets/admin_password.txt
```

### Production Security Settings

```bash
# Production .env
ENVIRONMENT="production"
ADMIN_USERNAME="prod-admin"
ADMIN_PASSWORD="UltraSecurePassword123!"

# Enhanced security
CRUD_ADMIN_REDIS_ENABLED=true
CRUD_ADMIN_REDIS_HOST="redis.internal.company.com"
CRUD_ADMIN_REDIS_PASSWORD="secure-redis-password"
CRUD_ADMIN_REDIS_SSL=true

# Monitoring
CRUD_ADMIN_TRACK_EVENTS=true
CRUD_ADMIN_TRACK_SESSIONS=true
SESSION_SECURE_COOKIES=true
CRUD_ADMIN_MAX_SESSIONS=5
CRUD_ADMIN_SESSION_TIMEOUT=480      # 8 hours
```

## Application User Management

### Admin vs Application Users

Your boilerplate maintains two separate user systems:

- **Admin Users**: Access the admin panel (stored by CRUDAdmin)
- **Application Users**: Use your application (stored in your User model)

### Managing Application Users

Through the admin panel, you can manage your application's users:

1. Navigate to "Users" section (your application users)
2. View, create, update user profiles
3. Manage user tiers and subscriptions
4. View user-generated content (posts)

The User model is already registered with password hashing and proper permissions.

## Emergency Recovery

### Lost Admin Password

If you lose admin access, update your environment variables:

```bash
# Update .env file
ADMIN_USERNAME="emergency-admin"
ADMIN_PASSWORD="EmergencyPassword123!"

# Restart application
uv run fastapi dev
```

### Database Recovery (Advanced)

For direct database password reset:

```python
# Generate bcrypt hash
import bcrypt
password = "NewPassword123!"
hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
print(hashed.decode('utf-8'))
```

```sql
-- Update in database
UPDATE admin_users 
SET password_hash = '<bcrypt-hash>' 
WHERE username = 'admin';
```

## What's Next

Your admin user management is now configured with:

- Automatic admin user creation from environment variables
- Secure authentication separate from application users
- Environment-specific security settings
- Production-ready credential management
- Emergency recovery procedures

You can now securely manage both admin users and your application users through the admin panel.
