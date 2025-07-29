import asyncio
import os
import hashlib

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.types import Message, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import AsyncClient

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FK_API_KEY = os.getenv("FK_API_KEY")
FK_SHOP_ID = os.getenv("FK_SHOP_ID")
FK_SECRET_KEY = os.getenv("FK_SECRET_KEY")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# FastAPI app
app = FastAPI()

# FSM: покупка UC
class BuyUC(StatesGroup):
    choosing_package = State()
    entering_id = State()

PACKAGE_PRICES = {
    "60": 70,
    "325": 320,
    "660": 610,
    "1800": 1650
}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    order_id = data.get("order_id")
    amount = data.get("amount")
    sign = data.get("sign")

    raw = f"{order_id}:{amount}:{FK_SECRET_KEY}"
    expected = hashlib.md5(raw.encode()).hexdigest()

    if sign != expected:
        return JSONResponse(content={"status": "error", "message": "bad signature"}, status_code=400)

    print(f"[✅] Оплата подтверждена: {order_id}")
    return {"status": "ok"}

@dp.message(F.text == "/start")
async def start_handler(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить UC", callback_data="buy_menu")]
    ])
    await message.answer("Добро пожаловать в UC SHOP!", reply_markup=kb)

@dp.callback_query(F.data == "buy_menu")
async def buy_menu(callback: types.CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="60 UC – 70₽", callback_data="buy_60")],
        [InlineKeyboardButton(text="325 UC – 320₽", callback_data="buy_325")],
        [InlineKeyboardButton(text="660 UC – 610₽", callback_data="buy_660")],
        [InlineKeyboardButton(text="1800 UC – 1650₽", callback_data="buy_1800")]
    ])
    await callback.message.answer("Выберите нужный пакет UC:", reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def choose_package(callback: types.CallbackQuery, state: FSMContext):
    package = callback.data.replace("buy_", "")
    await state.update_data(package=package)
    await callback.message.answer(f"Введите ваш PUBG ID для {package} UC:")
    await state.set_state(BuyUC.entering_id)
    await callback.answer()

async def create_fk_order(amount, order_id, email, ip="127.0.0.1"):
    url = "https://api.fk.life/v1/orders/create"
    headers = {
        "api-key": FK_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "shop_id": FK_SHOP_ID,
        "amount": amount,
        "currency": "RUB",
        "order_id": order_id,
        "email": email,
        "ip": ip,
        "i": 44,
        "success_url": "https://t.me/YOUR_BOT_NAME",
        "fail_url": "https://t.me/YOUR_BOT_NAME"
    }
    async with AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        return resp.json().get("Location")

@dp.message(BuyUC.entering_id)
async def receive_pubg_id(message: Message, state: FSMContext):
    data = await state.get_data()
    package = data["package"]
    price = PACKAGE_PRICES.get(package)
    pubg_id = message.text

    order_id = f"{message.from_user.id}_{package}"
    email = f"{message.from_user.id}@ucshop.pro"

    try:
        link = await create_fk_order(price, order_id, email)
        await message.answer(
            f"""✅ Ваш заказ: <b>{package} UC</b>
🎮 PUBG ID: <code>{pubg_id}</code>

💳 Оплатите по ссылке:
<a href="{link}">Перейти к оплате</a>
""", disable_web_page_preview=True
        )
    except Exception as e:
        print(f"[❌] Ошибка заказа: {e}")
        await message.answer("❌ Не удалось создать заказ. Попробуйте позже.")

    await state.clear()

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(dp.start_polling(bot))
