from aiogram.types import Message
from opentele.tl import TelegramClient
from opentele.api import APIData
import asyncio
import aiohttp
import time
import json
import shutil
import sqlite3

from config import API_ID, API_HASH
from database import db


class LolzApi:
    def __init__(self, token: str):
        self.__headers = {
            "Authorization": f"Bearer {token}",
        }
        self.__last_request_time = 0

    async def __make_request(self, url: str, method: str, rate_limit: float, params: dict = None) -> dict:
        current_time = time.time()

        while int(current_time - self.__last_request_time) < rate_limit:
            current_time = time.time()
            await asyncio.sleep(0.1)

        self.__last_request_time = current_time

        async with aiohttp.ClientSession(headers=self.__headers) as session:
            async with session.request(method, url, params=params) as response:
                return await response.json()

    async def search_telegram(self, **kwargs) -> dict:
        params = {
            **kwargs,
            'spam': 'no'
        }
        url = 'https://api.lzt.market/telegram'

        items = await self.__make_request(url=url, params=params, method='get', rate_limit=3)
        return items

    async def buy_item(self, item_id: int) -> dict:
        bought_item = await self.__make_request(
            url=f'https://api.lzt.market/{item_id}/fast-buy',
            method='post',
            rate_limit=0.5
        )
        return bought_item

    async def validate_token(self) -> bool:
        me = await self.__make_request(
            url=f'https://api.lzt.market/me',
            method='get',
            rate_limit=0.5
        )

        if 'user' in me:
            return True

        return False

async def build_api_data(json_file: dict) -> APIData:
    return APIData(
        api_id=json_file.get("app_id"),
        api_hash=json_file.get("app_hash"),
        device_model=json_file.get("device"),
        system_version=json_file.get("sdk"),
        app_version=json_file.get("app_version"),
        lang_code=json_file.get("lang_code"),
        system_lang_code=json_file.get("system_lang_code"),
        lang_pack=json_file.get("lang_pack"),
    )

async def validate_account(phone: str):
    with open(f'data/accounts/sessions/{phone}.json', 'r', encoding='utf-8') as f:
        session_json = json.load(f)

    client = TelegramClient(
        session=f'data/accounts/sessions/{phone}.session',
        api=await build_api_data(session_json)
    )
    await client.connect()

    account_validated = await client.is_user_authorized()

    await client.disconnect()

    return account_validated

async def create_session(authkey: str, dc_id: int, phone_number: str, session_json: dict ):
    shutil.copy('data/session_ref.session', f'data/accounts/sessions/{phone_number}.session')

    with open(f'data/accounts/sessions/{phone_number}.json', 'w', encoding='utf-8') as f:
        json.dump(session_json, f, ensure_ascii=False, indent=4)

    conn = sqlite3.connect(f'data/accounts/sessions/{phone_number}.session')
    cursor = conn.cursor()

    insert_query = '''
    INSERT INTO sessions (dc_id, server_address, port, auth_key, takeout_id)
    VALUES (?, ?, ?, ?, ?)
    '''

    dc_connections = {
        1: '149.154.175.53',
        2: '149.154.167.51',
        3: '149.154.175.100',
        4: '149.154.167.91',
        5: '91.108.56.130',
    }

    data = (dc_id, dc_connections[dc_id], 443, bytes.fromhex(authkey), None)
    cursor.execute(insert_query, data)
    conn.commit()

async def process_buying(message: Message, token: str, pmin: int, pmax: int,
                         count: int, origin: str, country: str, expectation_days: int):
    lolz_api = LolzApi(token)

    # Убираем вызов upper() и обеспечиваем, что country всегда список
    country_list = country if isinstance(country, list) else [country]
    
    all_items = (await lolz_api.search_telegram(pmin=pmin, pmax=pmax, origin=[origin], country=country_list, daybreak=expectation_days))['items']

    await message.answer(f'Найдено {len(all_items)} аккаунтов по Вашему запросу на первой странице, купим всё до {count}!')

    accounts_counter = 0
    for item in all_items:
        if accounts_counter >= count:
            break

        bought_account = await lolz_api.buy_item(item['item_id'])

        if 'errors' in bought_account:
            await message.answer(
                f'При покупке аккаунта произошла ошибка: `{bought_account['errors']}`',
                parse_mode='markdown'
            )
            continue

        bought_account = bought_account['item']
        session_json = json.loads(bought_account['telegram_json'])

        await create_session(
            bought_account['login'], int(bought_account['loginData']['password']),
            bought_account['telegram_phone'], session_json
        )
        session_name = f'{bought_account['telegram_phone']}.session'
        account_validated = await validate_account(bought_account['telegram_phone'])

        db.add_account(bought_account['telegram_phone'], session_name)
        db.add_bought_account(bought_account['telegram_phone'], session_name, item['item_id'])

        await message.answer(f'Удалось купить аккаунт - {bought_account['telegram_phone']}\nСтатус: {'валид' if account_validated else 'невалид'}')

        accounts_counter += 1

    await message.answer('Автопокупка завершена!')



