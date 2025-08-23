"""Admin API endpoints for platform administration."""

from fastapi import APIRouter

from .networks import router as networks_router
from .tenants import router as tenants_router

router = APIRouter(prefix="/admin")
router.include_router(tenants_router)
router.include_router(networks_router)
