from fastapi import APIRouter

from ..api.admin import router as admin_router
from ..api.v1 import router as v1_router

router = APIRouter(prefix="/api")
router.include_router(v1_router)
router.include_router(admin_router)
