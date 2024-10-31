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
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder, ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import Message, ContentType, CallbackQuery
import asyncio
from aiogram import Bot, Dispatcher, types, Router
from aiogram.enums import ParseMode

from aiogram.filters import Command, StateFilter, CommandStart
from aiogram.fsm.context import FSMContext

logging.basicConfig(level=logging.INFO)
# Объект бота
bot = Bot(token=config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode='HTML'))
# Диспетчер
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(f'Бу! Испугался? не бойся, я твой друг)',
                         parse_mode=ParseMode.HTML)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')
