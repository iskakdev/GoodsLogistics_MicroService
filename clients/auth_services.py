import httpx
from fastapi import HTTPException
from config import MARKETPLACE_URL


async def verify_access_token(token: str):
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            response = await client.get(f'{MARKETPLACE_URL}/auth/verify/',
                                        headers={'Authorization': f'Bearer {token}'})
    except httpx.RequestError:
        raise HTTPException(status_code=500, detail='Auth service не доступен')
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail='Access token не правильно или просрочен')
    elif response.status_code != 200:
        raise HTTPException(status_code=503, detail='Ошибка')
    try:
        user_db = response.json()
        return {
            "id": int(user_db['id']),
            "username": user_db['username'],
            "status": user_db['status']
        }
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=500, detail='Неправильные данные')
