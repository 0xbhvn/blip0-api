from crudadmin import CRUDAdmin
from crudadmin.admin_interface.model_view import PasswordTransformer

from ..core.security import get_password_hash
from ..models.tier import Tier
from ..models.user import User
from ..schemas.tier import TierCreate, TierUpdate
from ..schemas.user import UserCreate, UserUpdate


def register_admin_views(admin: CRUDAdmin) -> None:
    """Register all models and their schemas with the admin interface.

    This function adds all available models to the admin interface with appropriate
    schemas and permissions.
    """

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
        allowed_actions={"view", "create", "update", "delete"},
    )
