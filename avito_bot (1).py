import logging
import sqlite3
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.callback_data import CallbackData
import asyncio
from datetime import datetime
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота (замените на ваш)
API_TOKEN = 'YOUR_BOT_TOKEN_HERE'

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Callback data для кнопок
admin_cb = CallbackData('admin', 'action', 'listing_id')
listing_cb = CallbackData('listing', 'action', 'listing_id')

# Категории товаров
CATEGORIES = {
    'electronics': '📱 Электроника',
    'food': '🍕 Питание', 
    'clothing': '👕 Одежда',
    'other': '🔧 Разное'
}

# Состояния для FSM
class ListingStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_photo = State()
    waiting_for_category = State()
    waiting_for_shop_price = State()
    waiting_for_my_price = State()
    waiting_for_quantity = State()

class AdminStates(StatesGroup):
    waiting_for_admin_id = State()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица объявлений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            photo_id TEXT,
            category TEXT NOT NULL,
            shop_price REAL NOT NULL,
            my_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            approved_by INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Функции для работы с базой данных
def get_user_role(user_id):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def add_user(user_id, username, first_name):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def make_admin(user_id):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', ('admin', user_id))
    conn.commit()
    conn.close()

def add_listing(user_id, title, description, photo_id, category, shop_price, my_price, quantity):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO listings (user_id, title, description, photo_id, category, shop_price, my_price, quantity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, title, description, photo_id, category, shop_price, my_price, quantity))
    listing_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return listing_id

def get_pending_listings():
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.id, l.title, l.description, l.category, l.shop_price, l.my_price, l.quantity, u.username
        FROM listings l
        JOIN users u ON l.user_id = u.user_id
        WHERE l.status = 'pending'
        ORDER BY l.created_at
    ''')
    results = cursor.fetchall()
    conn.close()
    return results

def get_approved_listings(category=None):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    
    if category:
        cursor.execute('''
            SELECT l.id, l.title, l.description, l.photo_id, l.category, l.shop_price, l.my_price, l.quantity, u.username
            FROM listings l
            JOIN users u ON l.user_id = u.user_id
            WHERE l.status = 'approved' AND l.category = ?
            ORDER BY l.created_at DESC
        ''', (category,))
    else:
        cursor.execute('''
            SELECT l.id, l.title, l.description, l.photo_id, l.category, l.shop_price, l.my_price, l.quantity, u.username
            FROM listings l
            JOIN users u ON l.user_id = u.user_id
            WHERE l.status = 'approved'
            ORDER BY l.created_at DESC
        ''')
    
    results = cursor.fetchall()
    conn.close()
    return results

def approve_listing(listing_id, admin_id):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE listings 
        SET status = 'approved', approved_at = CURRENT_TIMESTAMP, approved_by = ?
        WHERE id = ?
    ''', (admin_id, listing_id))
    conn.commit()
    conn.close()

def reject_listing(listing_id):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE listings SET status = ? WHERE id = ?', ('rejected', listing_id))
    conn.commit()
    conn.close()

def get_listing_by_id(listing_id):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, u.username, u.first_name
        FROM listings l
        JOIN users u ON l.user_id = u.user_id
        WHERE l.id = ?
    ''', (listing_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_user_listings(user_id):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, category, shop_price, my_price, quantity, status, created_at
        FROM listings
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,))
    results = cursor.fetchall()
    conn.close()
    return results

# Клавиатуры
def get_main_keyboard(user_role):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    
    keyboard.add(KeyboardButton("📱 Каталог товаров"))
    keyboard.add(KeyboardButton("➕ Добавить объявление"))
    keyboard.add(KeyboardButton("📋 Мои объявления"))
    
    if user_role == 'admin':
        keyboard.add(KeyboardButton("⚙️ Админ панель"))
    
    return keyboard

def get_categories_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    for category_key, category_name in CATEGORIES.items():
        keyboard.insert(InlineKeyboardButton(category_name, 
                                           callback_data=f"category_{category_key}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_catalog"))
    return keyboard

def get_category_selection_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for category_name in CATEGORIES.values():
        keyboard.insert(KeyboardButton(category_name))
    return keyboard

def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📝 Ожидающие модерации"))
    keyboard.add(KeyboardButton("👤 Добавить админа"))
    keyboard.add(KeyboardButton("📊 Статистика"))
    keyboard.add(KeyboardButton("🔙 Главное меню"))
    return keyboard

# Обработчики команд
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    add_user(user_id, username, first_name)
    user_role = get_user_role(user_id)
    
    welcome_text = f"""
🛍️ Добро пожаловать в торговую площадку!

Вы можете:
• Просматривать каталог товаров по категориям
• Добавлять свои объявления
• Управлять своими товарами

Ваша роль: {"Администратор" if user_role == 'admin' else "Пользователь"}
    """
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_role))

# Главное меню
@dp.message_handler(text="🔙 Главное меню")
async def main_menu(message: types.Message):
    user_role = get_user_role(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(user_role))

# Каталог товаров
@dp.message_handler(text="📱 Каталог товаров")
async def show_catalog_categories(message: types.Message):
    text = "🛍️ Выберите категорию товаров:"
    await message.answer(text, reply_markup=get_categories_keyboard())

@dp.callback_query_handler(lambda c: c.data.startswith('category_'))
async def show_category_listings(callback_query: types.CallbackQuery):
    category_key = callback_query.data.replace('category_', '')
    category_name = CATEGORIES.get(category_key, 'Неизвестная категория')
    
    listings = get_approved_listings(category_key)
    
    if not listings:
        await callback_query.message.edit_text(
            f"📭 В категории '{category_name}' пока нет товаров.",
            reply_markup=get_categories_keyboard()
        )
        return
    
    await callback_query.message.delete()
    
    for listing in listings:
        listing_id, title, description, photo_id, category, shop_price, my_price, quantity, username = listing
        
        text = f"""
🛍️ <b>{title}</b>
📂 Категория: {CATEGORIES.get(category, 'Неизвестно')}
👤 Продавец: @{username if username else 'Не указан'}

📝 {description}

💰 <b>Цена магазина:</b> {shop_price} ₽
💵 <b>Моя цена:</b> {my_price} ₽
📦 <b>Количество:</b> {quantity} шт.

#товар_{listing_id}
        """
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("💬 Связаться с продавцом", 
                                        callback_data=listing_cb.new(action='contact', listing_id=listing_id)))
        
        if photo_id:
            await callback_query.message.answer_photo(photo_id, caption=text, parse_mode='HTML', reply_markup=keyboard)
        else:
            await callback_query.message.answer(text, parse_mode='HTML', reply_markup=keyboard)
    
    # Добавляем кнопку "Назад к категориям"
    back_keyboard = InlineKeyboardMarkup()
    back_keyboard.add(InlineKeyboardButton("🔙 Назад к категориям", callback_data="back_to_catalog"))
    await callback_query.message.answer("Выберите другую категорию:", reply_markup=back_keyboard)

@dp.callback_query_handler(lambda c: c.data == 'back_to_catalog')
async def back_to_catalog(callback_query: types.CallbackQuery):
    text = "🛍️ Выберите категорию товаров:"
    await callback_query.message.edit_text(text, reply_markup=get_categories_keyboard())

# Добавление объявления
@dp.message_handler(text="➕ Добавить объявление")
async def start_add_listing(message: types.Message):
    await ListingStates.waiting_for_title.set()
    await message.answer("📝 Введите название товара:")

@dp.message_handler(state=ListingStates.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await ListingStates.waiting_for_description.set()
    await message.answer("📄 Введите описание товара:")

@dp.message_handler(state=ListingStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await ListingStates.waiting_for_photo.set()
    
    skip_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    skip_keyboard.add(KeyboardButton("⏭️ Пропустить фото"))
    
    await message.answer("📸 Отправьте фото товара или нажмите 'Пропустить фото':", 
                        reply_markup=skip_keyboard)

@dp.message_handler(content_types=['photo'], state=ListingStates.waiting_for_photo)
async def process_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await ListingStates.waiting_for_category.set()
    await message.answer("📂 Выберите категорию товара:", 
                        reply_markup=get_category_selection_keyboard())

@dp.message_handler(text="⏭️ Пропустить фото", state=ListingStates.waiting_for_photo)
async def skip_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=None)
    await ListingStates.waiting_for_category.set()
    await message.answer("📂 Выберите категорию товара:", 
                        reply_markup=get_category_selection_keyboard())

@dp.message_handler(lambda message: message.text in CATEGORIES.values(), state=ListingStates.waiting_for_category)
async def process_category(message: types.Message, state: FSMContext):
    # Находим ключ категории по названию
    category_key = None
    for key, value in CATEGORIES.items():
        if value == message.text:
            category_key = key
            break
    
    if category_key:
        await state.update_data(category=category_key)
        await ListingStates.waiting_for_shop_price.set()
        await message.answer("💰 Введите цену магазина (в рублях):", 
                            reply_markup=types.ReplyKeyboardRemove())
    else:
        await message.answer("❌ Пожалуйста, выберите категорию из предложенных вариантов.")

@dp.message_handler(state=ListingStates.waiting_for_shop_price)
async def process_shop_price(message: types.Message, state: FSMContext):
    try:
        shop_price = float(message.text.replace(',', '.'))
        if shop_price <= 0:
            raise ValueError
        await state.update_data(shop_price=shop_price)
        await ListingStates.waiting_for_my_price.set()
        await message.answer("💵 Введите вашу цену (в рублях):")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную цену (число больше 0):")

@dp.message_handler(state=ListingStates.waiting_for_my_price)
async def process_my_price(message: types.Message, state: FSMContext):
    try:
        my_price = float(message.text.replace(',', '.'))
        if my_price <= 0:
            raise ValueError
        await state.update_data(my_price=my_price)
        await ListingStates.waiting_for_quantity.set()
        await message.answer("📦 Введите количество товара:")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную цену (число больше 0):")

@dp.message_handler(state=ListingStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if quantity <= 0:
            raise ValueError
        
        data = await state.get_data()
        listing_id = add_listing(
            message.from_user.id,
            data['title'],
            data['description'],
            data.get('photo_id'),
            data['category'],
            data['shop_price'],
            my_price,
            quantity
        )
        
        await state.finish()
        
        user_role = get_user_role(message.from_user.id)
        category_name = CATEGORIES.get(data['category'], 'Неизвестно')
        await message.answer(
            f"✅ Объявление создано! ID: {listing_id}\n"
            f"📂 Категория: {category_name}\n"
            "Ожидает модерации администратором.",
            reply_markup=get_main_keyboard(user_role)
        )
        
        # Уведомление админам о новом объявлении
        await notify_admins_new_listing(listing_id)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное количество (целое число больше 0):")

# Мои объявления
@dp.message_handler(text="📋 Мои объявления")
async def show_my_listings(message: types.Message):
    user_listings = get_user_listings(message.from_user.id)
    
    if not user_listings:
        await message.answer("📭 У вас пока нет объявлений.")
        return
    
    text = "📋 <b>Ваши объявления:</b>\n\n"
    
    for listing in user_listings:
        listing_id, title, category, shop_price, my_price, quantity, status, created_at = listing
        status_emoji = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌'
        }
        status_text = {
            'pending': 'На модерации',
            'approved': 'Одобрено',
            'rejected': 'Отклонено'
        }
        
        category_name = CATEGORIES.get(category, 'Неизвестно')
        
        text += f"{status_emoji.get(status, '❓')} <b>{title}</b>\n"
        text += f"📂 Категория: {category_name}\n"
        text += f"💰 Цена магазина: {shop_price} ₽ | Моя цена: {my_price} ₽\n"
        text += f"📦 Количество: {quantity} шт.\n"
        text += f"📊 Статус: {status_text.get(status, 'Неизвестно')}\n"
        text += f"📅 Создано: {created_at[:16]}\n\n"
    
    await message.answer(text, parse_mode='HTML')

# Админ панель
@dp.message_handler(text="⚙️ Админ панель")
async def admin_panel(message: types.Message):
    user_role = get_user_role(message.from_user.id)
    if user_role != 'admin':
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    await message.answer("⚙️ <b>Админ панель</b>", 
                        parse_mode='HTML', 
                        reply_markup=get_admin_keyboard())

# Ожидающие модерации
@dp.message_handler(text="📝 Ожидающие модерации")
async def show_pending_listings(message: types.Message):
    user_role = get_user_role(message.from_user.id)
    if user_role != 'admin':
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    pending_listings = get_pending_listings()
    
    if not pending_listings:
        await message.answer("📭 Нет объявлений, ожидающих модерации.")
        return
    
    for listing in pending_listings:
        listing_id, title, description, category, shop_price, my_price, quantity, username = listing
        
        category_name = CATEGORIES.get(category, 'Неизвестно')
        
        text = f"""
📝 <b>Новое объявление #{listing_id}</b>
👤 Автор: @{username if username else 'Не указан'}

🛍️ <b>{title}</b>
📂 Категория: {category_name}
📄 {description}

💰 <b>Цена магазина:</b> {shop_price} ₽
💵 <b>Моя цена:</b> {my_price} ₽
📦 <b>Количество:</b> {quantity} шт.
        """
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("✅ Одобрить", 
                               callback_data=admin_cb.new(action='approve', listing_id=listing_id)),
            InlineKeyboardButton("❌ Отклонить", 
                               callback_data=admin_cb.new(action='reject', listing_id=listing_id))
        )
        keyboard.add(
            InlineKeyboardButton("👁️ Подробнее", 
                               callback_data=admin_cb.new(action='details', listing_id=listing_id))
        )
        
        await message.answer(text, parse_mode='HTML', reply_markup=keyboard)

# Добавить админа
@dp.message_handler(text="👤 Добавить админа")
async def add_admin_start(message: types.Message):
    user_role = get_user_role(message.from_user.id)
    if user_role != 'admin':
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    await AdminStates.waiting_for_admin_id.set()
    await message.answer("👤 Введите ID пользователя, которого хотите сделать администратором:")

@dp.message_handler(state=AdminStates.waiting_for_admin_id)
async def process_admin_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        make_admin(user_id)
        await state.finish()
        await message.answer(f"✅ Пользователь {user_id} назначен администратором.")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректный ID пользователя (число):")

# Статистика
@dp.message_handler(text="📊 Статистика")
async def show_statistics(message: types.Message):
    user_role = get_user_role(message.from_user.id)
    if user_role != 'admin':
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    
    # Статистика пользователей
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
    total_admins = cursor.fetchone()[0]
    
    # Статистика объявлений
    cursor.execute('SELECT COUNT(*) FROM listings')
    total_listings = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM listings WHERE status = "pending"')
    pending_listings = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM listings WHERE status = "approved"')
    approved_listings = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM listings WHERE status = "rejected"')
    rejected_listings = cursor.fetchone()[0]
    
    # Статистика по категориям
    cursor.execute('''
        SELECT category, COUNT(*) 
        FROM listings 
        WHERE status = "approved" 
        GROUP BY category
    ''')
    category_stats = cursor.fetchall()
    
    conn.close()
    
    text = f"""
📊 <b>Статистика бота</b>

👥 <b>Пользователи:</b>
• Всего: {total_users}
• Администраторов: {total_admins}

📝 <b>Объявления:</b>
• Всего: {total_listings}
• На модерации: {pending_listings}
• Одобрено: {approved_listings}
• Отклонено: {rejected_listings}

📂 <b>По категориям (одобренные):</b>
"""
    
    for category_key, count in category_stats:
        category_name = CATEGORIES.get(category_key, 'Неизвестно')
        text += f"• {category_name}: {count}\n"
    
    await message.answer(text, parse_mode='HTML')

# Обработчики callback'ов
@dp.callback_query_handler(admin_cb.filter())
async def process_admin_callback(callback_query: types.CallbackQuery, callback_data: dict):
    action = callback_data['action']
    listing_id = int(callback_data['listing_id'])
    
    user_role = get_user_role(callback_query.from_user.id)
    if user_role != 'admin':
        await callback_query.answer("❌ У вас нет прав администратора.", show_alert=True)
        return
    
    if action == 'approve':
        approve_listing(listing_id, callback_query.from_user.id)
        await callback_query.answer("✅ Объявление одобрено!", show_alert=True)
        
        # Уведомить автора объявления
        listing = get_listing_by_id(listing_id)
        if listing:
            try:
                await bot.send_message(
                    listing[1],  # user_id
                    f"✅ Ваше объявление '{listing[2]}' было одобрено и опубликовано!"
                )
            except:
                pass
        
        await callback_query.message.edit_reply_markup()
    
    elif action == 'reject':
        reject_listing(listing_id)
        await callback_query.answer("❌ Объявление отклонено!", show_alert=True)
        
        # Уведомить автора объявления
        listing = get_listing_by_id(listing_id)
        if listing:
            try:
                await bot.send_message(
                    listing[1],  # user_id
                    f"❌ Ваше объявление '{listing[2]}' было отклонено администратором."
                )
            except:
                pass
        
        await callback_query.message.edit_reply_markup()
    
    elif action == 'details':
        listing = get_listing_by_id(listing_id)
        if listing:
            text = f"""
📋 <b>Подробная информация об объявлении #{listing_id}</b>

👤 <b>Автор:</b> {listing[12]} {listing[13]} (@{listing[11] if listing[11] else 'Не указан'})
🆔 <b>ID автора:</b> {listing[1]}

🛍️ <b>Название:</b> {listing[2]}
📂 <b>Категория:</b> {CATEGORIES.get(listing[5], 'Неизвестно')}
📄 <b>Описание:</b> {listing[3]}

💰 <b>Цена магазина:</b> {listing[6]} ₽
💵 <b>Моя цена:</b> {listing[7]} ₽
📦 <b>Количество:</b> {listing[8]} шт.

📊 <b>Статус:</b> {listing[9]}
📅 <b>Создано:</b> {listing[10][:16] if listing[10] else 'Не указано'}
            """
            
            if listing[4]:  # photo_id
                await callback_query.message.answer_photo(listing[4], caption=text, parse_mode='HTML')
            else:
                await callback_query.message.answer(text, parse_mode='HTML')
        
        await callback_query.answer()

@dp.callback_query_handler(listing_cb.filter())
async def process_listing_callback(callback_query: types.CallbackQuery, callback_data: dict):
    action = callback_data['action']
    listing_id = int(callback_data['listing_id'])
    
    if action == 'contact':
        listing = get_listing_by_id(listing_id)
        if listing:
            seller_username = listing[11]  # обновленный индекс
            if seller_username:
                await callback_query.answer(
                    f"Свяжитесь с продавцом: @{seller_username}",
                    show_alert=True
                )
            else:
                await callback_query.answer(
                    "У продавца не указан username в профиле",
                    show_alert=True
                )
        else:
            await callback_query.answer("Объявление не найдено", show_alert=True)

# Уведомление администраторов о новом объявлении
async def notify_admins_new_listing(listing_id):
    conn = sqlite3.connect('marketplace_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE role = "admin"')
    admin_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    listing = get_listing_by_id(listing_id)
    if listing:
        text = f"""
🔔 <b>Новое объявление для модерации!</b>

📝 ID: {listing_id}
🛍️ Название: {listing[2]}
📂 Категория: {CATEGORIES.get(listing[5], 'Неизвестно')}
👤 Автор: @{listing[11] if listing[11] else 'Не указан'}

Перейдите в админ панель для модерации.
        """
        
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, text, parse_mode='HTML')
            except:
                pass

if __name__ == '__main__':
    init_db()
    print("🚀 Бот запущен!")
    executor.start_polling(dp, skip_updates=True)