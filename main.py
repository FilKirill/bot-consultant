import asyncio
import logging
import gspread
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from oauth2client.service_account import ServiceAccountCredentials
from g4f import Provider, ChatCompletion
from config_reader import config
from data.db_session import global_init, create_session
from data.users import User
import concurrent.futures

# Логирование
logging.basicConfig(level=logging.INFO)

# Объект бота
bot = Bot(token=config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

# Инициализация базы данных
global_init('user.db')


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db_sess = create_session()
    user = db_sess.get(User, message.from_user.id)

    if user:
        await message.answer(f"👋 Привет, {user.name}! 👋")
        await show_subjects_keyboard(message)
    else:
        await message.answer("❌ Этот бот не для тебя ❌")


async def show_subjects_keyboard(message: types.Message):
    """Отправляет клавиатуру с предметами."""
    keyboard = InlineKeyboardBuilder()

    subjects = ["Кодинг", "Математика", "АЯ"]  # Предметы
    emojis = {"Кодинг": "💻", "Математика": "📐", "АЯ": "📚"}  # Эмодзи для предметов

    for subject in subjects:
        keyboard.add(
            types.InlineKeyboardButton(
                text=f"{emojis.get(subject, '📘')} {subject}",
                callback_data=f"subject_{subject}"
            )
        )

    await message.answer("📜 Выберите предмет, чтобы узнать свои долги:", reply_markup=keyboard.as_markup())


@dp.callback_query(lambda c: c.data.startswith("subject_"))
async def process_subject_callback(callback_query: CallbackQuery):
    """Обработчик выбора предмета."""
    subject = callback_query.data.split("_")[1]  # Получаем название предмета
    db_sess = create_session()
    user = db_sess.get(User, callback_query.from_user.id)

    if user:
        first_name = user.name
        waiting_message = await callback_query.message.answer("⌛ Ищем ваши долги...")

        # Асинхронно получаем долги пользователя
        debts = await get_debts_from_google_sheets(first_name)

        if subject in debts:
            sheet_data = debts[subject]
            header = sheet_data.get("header", [])
            scores = sheet_data.get("scores", [])

            if header and scores:
                below_50 = [header[i] for i, score in enumerate(scores) if score.isdigit() and int(score) < 50]

                if below_50:
                    await waiting_message.delete()
                    await show_themes_keyboard(subject, below_50, callback_query.message)
                else:
                    await waiting_message.edit_text(f"✅ У вас нет долгов по предмету *{subject}*!")
            else:
                await waiting_message.edit_text(f"❌ Нет данных по предмету *{subject}*.")
        else:
            await waiting_message.edit_text(f"❌ Нет данных по предмету *{subject}*.")
    else:
        await callback_query.message.answer("❌ Этот бот не для тебя ❌")


async def show_themes_keyboard(subject, themes, message):
    """Отправляет список тем-долгов по предмету с кнопками."""
    keyboard = InlineKeyboardBuilder()

    for theme in themes:
        keyboard.add(
            types.InlineKeyboardButton(
                text=theme,  # Название темы
                callback_data=f"debt_{subject}_{theme}"  # Данные для callback
            )
        )

    await message.answer(
        f"📚 Вот твои долги по предмету *{subject}*!\n\n"
        f"За помощью нажми на тему, по которой ты хочешь получить рекомендации:",
        reply_markup=keyboard.as_markup()
    )


@dp.callback_query(lambda c: c.data.startswith("debt_"))
async def process_debt_callback(callback_query: CallbackQuery):
    """Обработчик выбора темы для получения рекомендаций."""
    _, subject, theme = callback_query.data.split("_")  # Извлекаем предмет и тему

    await callback_query.message.answer(f"⌛ Ищу рекомендации для темы: *{theme}*...")

    # Формируем запрос к g4f
    prompt = f"Дай подробные рекомендации и советы для изучения темы '{theme}' по предмету '{subject}'. Включи примеры и полезные ресурсы."

    try:
        response = ChatCompletion.create(
            provider=Provider.ChatGpt,  # Используем ChatGPT
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            stream=False  # Можно включить stream для постепенной отправки
        )

        # Проверяем формат ответа
        if isinstance(response, list):  # Ответ в виде списка
            recommendations = "".join([msg["content"] for msg in response if "content" in msg])
        elif isinstance(response, dict) and "choices" in response:
            recommendations = response["choices"][0]["message"]["content"]
        else:
            recommendations = str(response)  # На случай неизвестного формата

        # Если рекомендаций нет, отправляем сообщение об этом
        if not recommendations.strip():
            recommendations = "К сожалению, не удалось получить рекомендации. Попробуйте позже."

        await callback_query.message.answer(
            f"📘 Рекомендации для темы *{theme}* по предмету *{subject}*:\n\n{recommendations}"
        )

    except Exception as e:
        await callback_query.message.answer("❌ Произошла ошибка при получении рекомендаций. Попробуйте позже.")
        logging.error(f"Ошибка при запросе к g4f: {e}")



async def get_debts_from_google_sheets(user_name):
    """Асинхронная обертка для получения данных из Google Sheets."""
    loop = asyncio.get_event_loop()

    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, fetch_debts, user_name)

    return result


def fetch_debts(user_name):
    """Получает данные из Google Sheets."""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name('secret_key.json', scope)
    client = gspread.authorize(credentials)

    spreadsheet = client.open('тест')  # Замените на имя вашей таблицы
    sheets = ['Кодинг', 'Математика', 'АЯ']

    results = {}
    for sheet in sheets:
        worksheet = spreadsheet.worksheet(sheet)

        try:
            # Используем поиск по имени
            cell = worksheet.find(user_name)
            row_data = worksheet.row_values(cell.row)
            header = worksheet.row_values(1)  # Темы — первая строка таблицы
            results[sheet] = {
                "header": header[1:],  # Пропускаем первую колонку (имена)
                "scores": row_data[1:]  # Пропускаем первую колонку (имя)
            }
        except gspread.exceptions.CellNotFound:
            # Пользователь не найден в этом листе
            continue

    return results


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')
