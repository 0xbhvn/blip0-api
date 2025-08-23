from fastapi import APIRouter

from .filter_scripts import router as filter_scripts_router
from .login import router as login_router
from .logout import router as logout_router
from .monitors import router as monitors_router
from .rate_limits import router as rate_limits_router
from .tasks import router as tasks_router
from .tenant import router as tenant_router
from .tiers import router as tiers_router
from .triggers import router as triggers_router
from .users import router as users_router

router = APIRouter(prefix="/v1")
router.include_router(login_router)
router.include_router(logout_router)
router.include_router(users_router)
router.include_router(tasks_router)
router.include_router(tiers_router)
router.include_router(rate_limits_router)
router.include_router(monitors_router)
router.include_router(triggers_router)
router.include_router(tenant_router)
router.include_router(filter_scripts_router)
