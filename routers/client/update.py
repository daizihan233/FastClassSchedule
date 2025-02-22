from fastapi import APIRouter, HTTPException, status

from utils import ci
from utils.config import config

router = APIRouter()

@router.get("/api/update")
async def api_update():
    match config.ci.kind:
        case "jenkins":
            return await ci.get_from_jenkins(config.ci.url, config.ci.filename)
        case _:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="未适配此 CI 类型")