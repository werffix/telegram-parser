import os
import asyncio
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, FloodWaitError
import logging
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ======================== КОНФИГ ИЗ .ENV ========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

# Проверка, что все данные загружены
if not all([BOT_TOKEN, API_ID, API_HASH]):
    raise ValueError("❌ Ошибка: Не найдены BOT_TOKEN, API_ID или API_HASH в файле .env")
# =========================================================

os.makedirs("sessions", exist_ok=True)
os.makedirs("results", exist_ok=True)

# Хранилище состояний пользователей
users = {}

def pretty_menu():
    return (
        "╔══════════════════════════════════╗\n"
        "║     🕵️ <b>TELEGRAM PARSER</b>       ║\n"
        "╠══════════════════════════════════╣\n"
        "║                                  ║\n"
        "║  📋 Собери username'ы всех, кто  ║\n"
        "║     когда-либо писал в группе!   ║\n"
        "║                                  ║\n"
        "║  ⚡ Быстро  •  🔒 Безопасно      ║\n"
        "║  📁 Результат в TXT файле        ║\n"
        "║                                  ║\n"
        "╚══════════════════════════════════╝\n\n"
        "🔧 <b>Команды:</b>\n"
        "  /start — Главное меню\n"
        "  /login — Авторизовать аккаунт\n"
        "  /parse — Начать парсинг\n"
        "  /help  — Инструкция\n\n"
        "👇 Нажми кнопку для начала:"
    )


async def send_formatted(bot, event, text, buttons=None):
    await event.respond(text, parse_mode='html', buttons=buttons, link_preview=False)


# Инициализация бота
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    users.setdefault(uid, {})
    await send_formatted(bot, event, pretty_menu(), buttons=[
        [Button.inline("🔐 Авторизация", b"cmd_login")],
        [Button.inline("🕵️ Начать парсинг", b"cmd_parse")],
        [Button.inline("📖 Инструкция", b"cmd_help")]
    ])


@bot.on(events.NewMessage(pattern='/help'))
@bot.on(events.CallbackQuery(data=b"cmd_help"))
async def help_handler(event):
    text = (
        "📖 <b>Инструкция по использованию</b>\n\n"
        "1️⃣ Нажми <b>«Авторизация»</b> и введи:\n"
        "   • API ID (число)\n"
        "   • API Hash (строка)\n"
        "   • Номер телефона (+7...)\n"
        "   • Код из Telegram\n"
        "   • 2FA пароль (если включён)\n\n"
        "2️⃣ Нажми <b>«Начать парсинг»</b> и отправь:\n"
        "   • Ссылку на группу (https://t.me/xxx)\n"
        "   • Или username (@xxx)\n\n"
        "3️⃣ Бот соберёт все username'ы из\n"
        "   сообщений и отправит TXT файл.\n\n"
        "⚠️ <b>Важно:</b>\n"
        "  • API ключи бери на my.telegram.org\n"
        "  • Аккаунт должен быть в группе\n"
        "  • Парсинг может занять время\n"
        "  • Бот не сохраняет ваши данные"
    )
    await event.respond(text, parse_mode='html')


@bot.on(events.CallbackQuery(data=b"cmd_login"))
async def login_start(event):
    uid = event.sender_id
    users.setdefault(uid, {})['step'] = 'api_id'
    await event.edit(
        "🔐 <b>Шаг 1/4 — API ID</b>\n\n"
        "Введи числовой <b>API ID</b>:\n"
        "<i>(получить на my.telegram.org)</i>",
        parse_mode='html'
    )


@bot.on(events.CallbackQuery(data=b"cmd_parse"))
async def parse_start(event):
    uid = event.sender_id
    u = users.get(uid, {})
    if 'client' not in u:
        await event.answer("⚠️ Сначала авторизуйся! Нажми /login", alert=True)
        return
    u['step'] = 'group_link'
    await event.edit(
        "🕵️ <b>Введи ссылку на группу</b>\n\n"
        "Примеры:\n"
        "  <code>https://t.me/groupname</code>\n"
        "  <code>@groupname</code>\n"
        "  <code>groupname</code>",
        parse_mode='html'
    )


@bot.on(events.NewMessage)
async def input_handler(event):
    # Игнорируем команды, чтобы они не попадали в логику ввода
    if event.text and event.text.startswith('/'):
        return

    uid = event.sender_id
    u = users.get(uid)
    if not u or 'step' not in u:
        return

    text = event.text.strip()
    step = u['step']

    # ---------- API ID ----------
    if step == 'api_id':
        try:
            u['api_id'] = int(text)
            u['step'] = 'api_hash'
            await event.respond("✅ <b>API ID принят!</b>\n\nТеперь введи <b>API Hash</b>:", parse_mode='html')
        except ValueError:
            await event.respond("❌ API ID — это число. Попробуй снова:")

    # ---------- API HASH ----------
    elif step == 'api_hash':
        u['api_hash'] = text
        u['step'] = 'phone'
        await event.respond("✅ <b>API Hash принят!</b>\n\nВведи <b>номер телефона</b> с кодом страны:\n<code>+79991234567</code>", parse_mode='html')

    # ---------- PHONE ----------
    elif step == 'phone':
        u['phone'] = text
        u['step'] = 'code'

        # Используем API ID/HASH из конфига бота для создания клиентской сессии пользователя
        # Но лучше использовать те, что ввел пользователь, если мы хотим универсальности.
        # В данном примере мы используем введенные пользователем API ID/Hash для его сессии.
        
        client = TelegramClient(f"sessions/user_{uid}", u['api_id'], u['api_hash'])
        await client.connect()

        if not await client.is_user_authorized():
            try:
                await client.send_code_request(text)
                u['client'] = client
                await event.respond("📱 <b>Код отправлен в Telegram!</b>\n\nВведи его сюда:")
            except Exception as e:
                await event.respond(f"❌ Ошибка: <code>{e}</code>")
                if uid in users: del users[uid]
        else:
            u['client'] = client
            u['me'] = await client.get_me() # Сохраняем информацию о пользователе
            u['step'] = 'ready'
            await event.respond("✅ <b>Ты уже авторизован!</b>\n\nМожешь начинать парсинг: /parse")

    # ---------- CODE ----------
    elif step == 'code':
        try:
            await u['client'].sign_in(u['phone'], text)
            u['me'] = await u['client'].get_me()
            u['step'] = 'ready'
            await event.respond(
                "🎉 <b>Авторизация успешна!</b>\n\n"
                "Теперь нажми <b>«Начать парсинг»</b> или введи /parse",
                parse_mode='html'
            )
        except SessionPasswordNeededError:
            u['step'] = 'password'
            await event.respond("🔒 <b>Включена 2FA!</b>\nВведи свой пароль облака:")
        except Exception as e:
            await event.respond(f"❌ Ошибка кода: <code>{e}</code>")

    # ---------- 2FA PASSWORD ----------
    elif step == 'password':
        try:
            await u['client'].sign_in(password=text)
            u['me'] = await u['client'].get_me()
            u['step'] = 'ready'
            await event.respond(
                "🎉 <b>Авторизация успешна!</b>\n\n"
                "Теперь нажми <b>«Начать парсинг»</b> или введи /parse",
                parse_mode='html'
            )
        except Exception as e:
            await event.respond(f"❌ Неверный пароль: <code>{e}</code>")

    # ---------- GROUP LINK ----------
    elif step == 'group_link':
        await event.respond("⏳ <b>Подключение к группе...</b>")

        try:
            # Определяем entity
            link = text.replace("https://t.me/", "").replace("http://t.me/", "").lstrip("@")
            
            status_msg = await event.respond(
                f"🕵️ <b>Поиск группы: {link}</b>..."
            )

            entity = await u['client'].get_entity(link)
            title = getattr(entity, 'title', link)

            await status_msg.edit(
                f"🕵️ <b>Парсинг группы: {title}</b>\n\n"
                f"📊 Обработано: <b>0</b> сообщений\n"
                f"👤 Найдено username: <b>0</b>"
            )

            usernames = set()
            count = 0
            start_time = datetime.now()

            # Парсинг сообщений
            async for message in u['client'].iter_messages(entity, limit=None):
                if message.sender and message.sender.username:
                    usernames.add(message.sender.username)
                count += 1

                if count % 500 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = count / elapsed if elapsed > 0 else 0
                    try:
                        await status_msg.edit(
                            f"🕵️ <b>Парсинг: {title}</b>\n\n"
                            f"📊 Обработано: <b>{count}</b> сообщений\n"
                            f"👤 Найдено username: <b>{len(usernames)}</b>\n"
                            f"⚡ Скорость: {speed:.1f} msg/сек",
                            parse_mode='html'
                        )
                    except FloodWaitError as e:
                        print(f"Flood wait: {e.seconds}")
                        await asyncio.sleep(e.seconds)

            # Сохраняем результат
            filename = f"results/user_{uid}_{int(datetime.now().timestamp())}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"📋 Username из группы: {title}\n")
                f.write(f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
                f.write(f"📊 Всего сообщений: {count}\n")
                f.write(f"👤 Уникальных username: {len(usernames)}\n")
                f.write("=" * 40 + "\n\n")
                for username in sorted(usernames):
                    f.write(f"@{username}\n")

            elapsed = (datetime.now() - start_time).total_seconds()

            await status_msg.edit(
                f"✅ <b>Парсинг завершён!</b>\n\n"
                f"📁 Группа: <b>{title}</b>\n"
                f"📊 Сообщений: <b>{count:,}</b>\n"
                f"👤 Username: <b>{len(usernames):,}</b>\n"
                f"⏱ Время: <b>{elapsed:.1f} сек</b>",
                parse_mode='html'
            )

            await event.respond("📁 <b>Файл с результатами:</b>", file=filename)

            # Очищаем файл после отправки (опционально)
            # os.remove(filename) 
            u['step'] = 'ready'

        except Exception as e:
            await event.respond(f"❌ <b>Ошибка:</b> <code>{e}</code>", parse_mode='html')
            u['step'] = 'ready'


if __name__ == "__main__":
    print("╔══════════════════════════════════╗")
    print("║     🕵️ TELEGRAM PARSER BOT       ║")
    print("╚══════════════════════════════════╝")
    bot.start()
    print("✅ Бот запущен и работает!")
    bot.run_until_disconnected()
