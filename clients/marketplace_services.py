import httpx
from fastapi import HTTPException
from config import MARKETPLACE_URL


async def get_object(path: str, token: str, not_found: str):
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            response = await client.get(f'{MARKETPLACE_URL.rstrip("/")}{path}',
                                        headers={'Authorization': f'Bearer {token}'})
    except httpx.RequestError:
        raise HTTPException(detail='Marketplace service недоступен', status_code=503)

    if response.status_code == 401:
        raise HTTPException(detail='Неверный токен', status_code=401)
    if response.status_code == 403:
        raise HTTPException(detail='Недостаточно прав', status_code=403)
    if response.status_code in (400, 404):
        raise HTTPException(detail=not_found, status_code=400)
    if response.status_code != 200:
        raise HTTPException(detail='Ошибка Marketplace service', status_code=502)

    try:
        return response.json()
    except ValueError:
        raise HTTPException(detail='Неправильные данные от Marketplace service', status_code=502)


async def get_city(city_id: int, token: str):
    return await get_object(f'/cities/{city_id}/', token, 'Город не найден')


async def get_product(product_id: int, token: str):
    return await get_object(f'/products/{product_id}/', token, 'Товар не найден')


async def get_order(order_id: int, token: str):
    return await get_object(f'/orders/{order_id}/', token, 'Заказ не найден')
