from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database.db import SessionLocal
from clients.auth_services import verify_access_token

bearer_schema = HTTPBearer()


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_schema)):
    current_user = await verify_access_token(credentials.credentials)
    current_user['token'] = credentials.credentials
    return current_user
