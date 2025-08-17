"""Admin API endpoints for platform administration."""

from fastapi import APIRouter

from .tenants import router as tenants_router

router = APIRouter(prefix="/admin")
router.include_router(tenants_router)
