from fastapi import APIRouter

from routers.web.configs.schedule import router as schedule_router
from routers.web.configs.subjects import router as subjects_router
from routers.web.configs.timetable import router as timetable_router
from routers.web.configs.setting import router as setting_router
from routers.web.configs.menu import router as menu_router

router = APIRouter()

router.include_router(schedule_router)
router.include_router(subjects_router)
router.include_router(timetable_router)
router.include_router(setting_router)
router.include_router(menu_router)
