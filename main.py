import math
import datetime
import os
import random
import re
import json
import difflib
import asyncio
import logging
from aiogram.client.default import DefaultBotProperties
from config_reader import config
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import Message, ContentType, CallbackQuery
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from data.db_session import global_init, create_session
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from data.users import User
from aiogram.fsm.state import StatesGroup, State
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import concurrent.futures

logging.basicConfig(level=logging.INFO)
# Объект бота
bot = Bot(token=config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode='HTML'))
# Диспетчер
dp = Dispatcher()
global_init('user.db')


# Определяем состояния для FSM
class UserStates(StatesGroup):
    waiting_for_name = State()  # Стейт больше не нужен, так как имя уже есть


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    db_sess = create_session()
    user = db_sess.get(User, message.from_user.id)

    if user:
        await message.answer(f"Привет! {user.name}")
        await show_debt_button(message)
    else:
        await message.answer("Этот бот не для тебя")


async def show_debt_button(message: types.Message):
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="Узнать свои долги", callback_data="check_debts"))
    await message.answer("Чтобы узнать свои долги, нажмите на кнопку ниже:", reply_markup=keyboard.as_markup())


# Асинхронная обертка для работы с Google Sheets
async def get_debts_from_google_sheets(user_name):
    loop = asyncio.get_event_loop()

    # Используем поток для работы с gspread, чтобы не блокировать основной поток
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, fetch_debts, user_name)

    return result


# Функция для получения данных из Google Sheets
def fetch_debts(user_name):
    # Настройка доступа к Google Sheets
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name('secret_key.json', scope)
    client = gspread.authorize(credentials)

    # Открываем таблицу и выбираем листы
    spreadsheet = client.open('тест')  # Замените на имя вашей таблицы
    sheets = ['Кодинг', 'Математика', 'АЯ']

    results = {}

    # Проходим по каждому листу и ищем пользователя
    for sheet in sheets:
        worksheet = spreadsheet.worksheet(sheet)
        data = worksheet.get_all_values()

        # Ищем пользователя в первом столбце
        for row in data[1:]:
            if row[0] == user_name:
                results[sheet] = row[2:]  # Все значения после имени

    return results


# Обработчик запроса долгов
@dp.callback_query(lambda c: c.data == "check_debts")
async def process_check_debts(callback_query: CallbackQuery, state: FSMContext):
    db_sess = create_session()
    user = db_sess.get(User, callback_query.from_user.id)

    if user:
        first_name = user.name  # Предполагаем, что имя и фамилия разделены пробелом

        # Асинхронно получаем долги пользователя
        debts = await get_debts_from_google_sheets(first_name)

        if debts:
            debt_info = "\n".join([f"{sheet}: {', '.join(scores)}" for sheet, scores in debts.items()])
            await callback_query.message.answer(f"Ваши долги:\n{debt_info}")
        else:
            await callback_query.message.answer("У вас нет долгов.")
    else:
        await callback_query.message.answer("У вас нет долгов.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')
