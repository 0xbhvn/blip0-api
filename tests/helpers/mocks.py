from typing import Any

from fastapi.encoders import jsonable_encoder

from src.app import models
from tests.conftest import fake


def get_current_user(user: models.User) -> dict[str, Any]:
    result = jsonable_encoder(user)
    return dict(result)  # Explicitly cast to dict to satisfy mypy


def oauth2_scheme() -> str:
    token = fake.sha256()
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token  # type: ignore
