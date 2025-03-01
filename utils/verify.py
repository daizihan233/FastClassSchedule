import secrets
from typing import Annotated

from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBasicCredentials, HTTPBasic
from loguru import logger

from utils.config import config

security = HTTPBasic()

def get_current_identity(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
):
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = b"ElectronClassSchedule"
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = config.secret.token.encode("utf8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )
    if not (is_correct_username and is_correct_password):
        logger.warning(f"收到需要密码验证的请求，但密码或用户名错误：{credentials.username}:{credentials.password}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误",
            headers={"WWW-Authenticate": "Basic"},
        )
    return f"{credentials.username}:{credentials.password}"