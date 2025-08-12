# Adding Models

Learn how to extend the admin interface with your new models by following the patterns established in the FastAPI boilerplate. The boilerplate already includes User, Tier, and Post models - we'll show you how to add your own models using these working examples.

> **CRUDAdmin Features**: This guide shows boilerplate-specific patterns. For advanced model configuration options and features, see the [CRUDAdmin documentation](https://benavlabs.github.io/crudadmin/).

## Understanding the Existing Setup

The boilerplate comes with three models already registered in the admin interface. Understanding how they're implemented will help you add your own models successfully.

### Current Model Registration

The admin interface is configured in `src/app/admin/views.py`:

```python
def register_admin_views(admin: CRUDAdmin) -> None:
    """Register all models and their schemas with the admin interface."""
    
    # User model with password handling
    password_transformer = PasswordTransformer(
        password_field="password",
        hashed_field="hashed_password", 
        hash_function=get_password_hash,
        required_fields=["name", "username", "email"],
    )
    
    admin.add_view(
        model=User,
        create_schema=UserCreate,
        update_schema=UserUpdate,
        allowed_actions={"view", "create", "update"},
        password_transformer=password_transformer,
    )

    admin.add_view(
        model=Tier,
        create_schema=TierCreate,
        update_schema=TierUpdate,
        allowed_actions={"view", "create", "update", "delete"}
    )

    admin.add_view(
        model=Post,
        create_schema=PostCreateAdmin,  # Special admin-only schema
        update_schema=PostUpdate,
        allowed_actions={"view", "create", "update", "delete"}
    )
```

Each model registration follows the same pattern: specify the SQLAlchemy model, appropriate Pydantic schemas for create/update operations, and define which actions are allowed.

## Step-by-Step Model Addition

Let's walk through adding a new model to your admin interface using a product catalog example.

### Step 1: Create Your Model

First, create your SQLAlchemy model following the boilerplate's patterns:

```python
# src/app/models/product.py
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Numeric, ForeignKey, Text, Boolean
from sqlalchemy.types import DateTime
from datetime import datetime

from ..core.db.database import Base

class Product(Base):
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Foreign key relationship (similar to Post.created_by_user_id)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
```

### Step 2: Create Pydantic Schemas

Create schemas for the admin interface following the boilerplate's pattern:

```python
# src/app/schemas/product.py
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Annotated

class ProductCreate(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=100)]
    description: Annotated[str | None, Field(max_length=1000, default=None)]
    price: Annotated[Decimal, Field(gt=0, le=999999.99)]
    is_active: Annotated[bool, Field(default=True)]
    category_id: Annotated[int, Field(gt=0)]

class ProductUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=2, max_length=100, default=None)]
    description: Annotated[str | None, Field(max_length=1000, default=None)]
    price: Annotated[Decimal | None, Field(gt=0, le=999999.99, default=None)]
    is_active: Annotated[bool | None, Field(default=None)]
    category_id: Annotated[int | None, Field(gt=0, default=None)]
```

### Step 3: Register with Admin Interface

Add your model to `src/app/admin/views.py`:

```python
# Add import at the top
from ..models.product import Product
from ..schemas.product import ProductCreate, ProductUpdate

def register_admin_views(admin: CRUDAdmin) -> None:
    """Register all models and their schemas with the admin interface."""
    
    # ... existing model registrations ...
    
    # Add your new model
    admin.add_view(
        model=Product,
        create_schema=ProductCreate,
        update_schema=ProductUpdate,
        allowed_actions={"view", "create", "update", "delete"}
    )
```

### Step 4: Create and Run Migration

Generate the database migration for your new model:

```bash
# Generate migration
uv run alembic revision --autogenerate -m "Add product model"

# Apply migration
uv run alembic upgrade head
```

### Step 5: Test Your New Model

Start your application and test the new model in the admin interface:

```bash
# Start the application
uv run fastapi dev

# Visit http://localhost:8000/admin
# Login with your admin credentials
# You should see "Products" in the admin navigation
```

## Learning from Existing Models

Each model in the boilerplate demonstrates different admin interface patterns you can follow.

### User Model - Password Handling

The User model shows how to handle sensitive fields like passwords:

```python
# Password transformer for secure password handling
password_transformer = PasswordTransformer(
    password_field="password",         # Field in the schema
    hashed_field="hashed_password",    # Field in the database model  
    hash_function=get_password_hash,   # Your app's hash function
    required_fields=["name", "username", "email"],  # Fields required for user creation
)

admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update"},  # No delete for users
    password_transformer=password_transformer,
)
```

**When to use this pattern:**

- Models with password fields
- Any field that needs transformation before storage
- Fields requiring special security handling

### Tier Model - Simple CRUD

The Tier model demonstrates straightforward CRUD operations:

```python
admin.add_view(
    model=Tier,
    create_schema=TierCreate,
    update_schema=TierUpdate,
    allowed_actions={"view", "create", "update", "delete"}  # Full CRUD
)
```

**When to use this pattern:**

- Reference data (categories, types, statuses)
- Configuration models
- Simple data without complex relationships

### Post Model - Admin-Specific Schemas

The Post model shows how to create admin-specific schemas when the regular API schemas don't work for admin purposes:

```python
# Special admin schema (different from regular PostCreate)
class PostCreateAdmin(BaseModel):
    title: Annotated[str, Field(min_length=2, max_length=30)]
    text: Annotated[str, Field(min_length=1, max_length=63206)]
    created_by_user_id: int  # Required in admin, but not in API
    media_url: Annotated[str | None, Field(pattern=r"^(https?|ftp)://[^\s/$.?#].[^\s]*$", default=None)]

admin.add_view(
    model=Post,
    create_schema=PostCreateAdmin,  # Admin-specific schema
    update_schema=PostUpdate,       # Regular update schema works fine
    allowed_actions={"view", "create", "update", "delete"}
)
```

**When to use this pattern:**

- Models where admins need to set fields that users can't
- Models requiring additional validation for admin operations
- Cases where API schemas are too restrictive or too permissive for admin use

## Advanced Model Configuration

### Customizing Field Display

You can control how fields appear in the admin interface by modifying your schemas:

```python
class ProductCreateAdmin(BaseModel):
    name: Annotated[str, Field(
        min_length=2, 
        max_length=100,
        description="Product name as shown to customers"
    )]
    description: Annotated[str | None, Field(
        max_length=1000,
        description="Detailed product description (supports HTML)"
    )]
    price: Annotated[Decimal, Field(
        gt=0, 
        le=999999.99,
        description="Price in USD (up to 2 decimal places)"
    )]
    category_id: Annotated[int, Field(
        gt=0,
        description="Product category (creates dropdown automatically)"
    )]
```

### Restricting Actions

Control what operations are available for each model:

```python
# Read-only model (reports, logs, etc.)
admin.add_view(
    model=AuditLog,
    create_schema=None,  # No creation allowed
    update_schema=None,  # No updates allowed
    allowed_actions={"view"}  # Only viewing
)

# No deletion allowed (users, critical data)
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update"}  # No delete
)
```

### Handling Complex Fields

Some models may have fields that don't work well in the admin interface. Use select schemas to exclude problematic fields:

```python
from pydantic import BaseModel

# Create a simplified view schema
class ProductAdminView(BaseModel):
    id: int
    name: str
    price: Decimal
    is_active: bool
    # Exclude complex fields like large text or binary data

admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    select_schema=ProductAdminView,  # Controls what's shown in lists
    allowed_actions={"view", "create", "update", "delete"}
)
```

## Common Model Patterns

### Reference Data Models

For categories, types, and other reference data:

```python
# Simple reference model
class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text)

# Simple schemas
class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    description: str | None = None

# Registration
admin.add_view(
    model=Category,
    create_schema=CategoryCreate,
    update_schema=CategoryCreate,  # Same schema for create and update
    allowed_actions={"view", "create", "update", "delete"}
)
```

### User-Generated Content

For content models with user associations:

```python
class BlogPost(Base):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)

# Admin schema with required author
class BlogPostCreateAdmin(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    content: str = Field(..., min_length=10)
    author_id: int = Field(..., gt=0)  # Admin must specify author
    published_at: datetime | None = None

admin.add_view(
    model=BlogPost,
    create_schema=BlogPostCreateAdmin,
    update_schema=BlogPostUpdate,
    allowed_actions={"view", "create", "update", "delete"}
)
```

### Configuration Models

For application settings and configuration:

```python
class SystemSetting(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

# Restricted actions - settings shouldn't be deleted
admin.add_view(
    model=SystemSetting,
    create_schema=SystemSettingCreate,
    update_schema=SystemSettingUpdate,
    allowed_actions={"view", "create", "update"}  # No delete
)
```

## Testing Your Models

After adding models to the admin interface, test them thoroughly:

### Manual Testing

1. **Access**: Navigate to `/admin` and log in
2. **Create**: Try creating new records with valid and invalid data
3. **Edit**: Test updating existing records
4. **Validation**: Verify that your schema validation works correctly
5. **Relationships**: Test foreign key relationships (dropdowns should populate)

### Development Testing

```python
# Test your admin configuration
# src/scripts/test_admin.py
from app.admin.initialize import create_admin_interface

def test_admin_setup():
    admin = create_admin_interface()
    if admin:
        print("Admin interface created successfully")
        print(f"Models registered: {len(admin._views)}")
        for model_name in admin._views:
            print(f"  - {model_name}")
    else:
        print("Admin interface disabled")

if __name__ == "__main__":
    test_admin_setup()
```

```bash
# Run the test
uv run python src/scripts/test_admin.py
```

## Updating Model Registration

When you need to modify how existing models appear in the admin interface:

### Adding Actions

```python
# Enable deletion for a model that previously didn't allow it
admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    allowed_actions={"view", "create", "update", "delete"}  # Added delete
)
```

### Changing Schemas

```python
# Switch to admin-specific schemas
admin.add_view(
    model=User,
    create_schema=UserCreateAdmin,    # New admin schema
    update_schema=UserUpdateAdmin,    # New admin schema  
    allowed_actions={"view", "create", "update"},
    password_transformer=password_transformer,
)
```

### Performance Optimization

For models with many records, consider using select schemas to limit data:

```python
# Only show essential fields in lists
class UserListView(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool

admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    select_schema=UserListView,  # Faster list loading
    allowed_actions={"view", "create", "update"},
    password_transformer=password_transformer,
)
```

## What's Next

With your models successfully added to the admin interface, you're ready to:

1. **[User Management](user-management.md)** - Learn how to manage admin users and implement security best practices

Your models are now fully integrated into the admin interface and ready for production use. The admin panel will automatically handle form generation, validation, and database operations based on your model and schema definitions. 