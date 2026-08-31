       # ПОЛНАЯ исправленная версия homework_bot_complete_fixed.py
# Восстановлены ВСЕ недостающие обработчики

import asyncio
import logging
import sqlite3
from datetime import datetime
import calendar
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto, InputMediaDocument
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from config_fixed import BOT_TOKEN, MASTER_PASSWORD, DATABASE_PATH, CALENDAR_MONTHS_RU, CALENDAR_WEEKDAYS_RU, MESSAGES, EMOJI

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для FSM
class GroupStates(StatesGroup):
    waiting_group_name = State()
    waiting_group_password = State()
    waiting_master_password = State()
    waiting_new_group_password = State()
    waiting_homework_subject = State()
    waiting_homework_text = State()
    waiting_homework_files = State()
    # Новые состояния для личного ДЗ
    waiting_personal_subject = State()
    waiting_personal_text = State()
    waiting_personal_files = State()

# Класс для работы с групповой базой данных
class DatabaseManager:
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    group_id INTEGER,
                    is_admin INTEGER DEFAULT 0,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES groups (id)
                )
            ''')
            
            cursor.execute("PRAGMA table_info(homework)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if not columns:
                cursor.execute('''
                    CREATE TABLE homework (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id INTEGER,
                        date TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        text TEXT NOT NULL,
                        files TEXT,
                        created_by INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (group_id) REFERENCES groups (id),
                        FOREIGN KEY (created_by) REFERENCES users (user_id)
                    )
                ''')
                logger.info("Создана таблица homework")
            else:
                if 'created_by' not in columns:
                    cursor.execute('ALTER TABLE homework ADD COLUMN created_by INTEGER')
                if 'created_at' not in columns:
                    cursor.execute('ALTER TABLE homework ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                if 'files' not in columns:
                    cursor.execute('ALTER TABLE homework ADD COLUMN files TEXT')
                logger.info("Обновлена структура таблицы homework")
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS homework_completion (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    homework_id INTEGER,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (homework_id) REFERENCES homework (id),
                    UNIQUE(user_id, homework_id)
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("База данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")
    
    def get_user_group(self, user_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT group_id, is_admin FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения группы пользователя: {e}")
            return None
    
    def get_group_name(self, group_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM groups WHERE id = ?', (group_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения названия группы: {e}")
            return None
    
    def group_exists(self, group_name):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM groups WHERE name = ?', (group_name,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except Exception as e:
            logger.error(f"Ошибка проверки существования группы: {e}")
            return False
    
    def check_group_password(self, group_name, password):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM groups WHERE name = ? AND password = ?', (group_name, password))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка проверки пароля группы: {e}")
            return None
    
    def create_group(self, group_name, password):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO groups (name, password) VALUES (?, ?)', (group_name, password))
            group_id = cursor.lastrowid
            conn.commit()
            conn.close()
            logger.info(f"Создана новая группа: {group_name}")
            return group_id
        except Exception as e:
            logger.error(f"Ошибка создания группы: {e}")
            return None
    
    def join_user_to_group(self, user_id, username, group_id, is_admin=False):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, group_id, is_admin) 
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, group_id, int(is_admin)))
            conn.commit()
            conn.close()
            logger.info(f"Пользователь {user_id} добавлен в группу {group_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя в группу: {e}")
            return False
    
    def get_homework_for_date(self, group_id, date, user_id=None):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute('''
                    SELECT h.id, h.subject, h.text, h.files,
                           CASE WHEN hc.homework_id IS NOT NULL THEN 1 ELSE 0 END as completed
                    FROM homework h
                    LEFT JOIN homework_completion hc ON h.id = hc.homework_id AND hc.user_id = ?
                    WHERE h.group_id = ? AND h.date = ?
                    ORDER BY h.subject
                ''', (user_id, group_id, date))
            else:
                cursor.execute('''
                    SELECT id, subject, text, files, 0 as completed
                    FROM homework 
                    WHERE group_id = ? AND date = ?
                    ORDER BY subject
                ''', (group_id, date))
            
            result = cursor.fetchall()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения ДЗ: {e}")
            return []
    
    def get_homework_dates_for_month(self, group_id, year, month, user_id=None):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            start_date = f"{year}-{month:02d}-01"
            if month == 12:
                end_date = f"{year + 1}-01-01"
            else:
                end_date = f"{year}-{month + 1:02d}-01"
            
            if user_id:
                cursor.execute('''
                    SELECT h.date,
                           COUNT(h.id) as total_homework,
                           COUNT(hc.homework_id) as completed_homework
                    FROM homework h
                    LEFT JOIN homework_completion hc ON h.id = hc.homework_id AND hc.user_id = ?
                    WHERE h.group_id = ? AND h.date >= ? AND h.date < ?
                    GROUP BY h.date
                ''', (user_id, group_id, start_date, end_date))
                
                result = {}
                for row in cursor.fetchall():
                    date, total, completed = row
                    if completed == total:
                        result[date] = "complete"
                    elif completed > 0:
                        result[date] = "partial"
                    else:
                        result[date] = "not_complete"
            else:
                cursor.execute('''
                    SELECT DISTINCT date FROM homework 
                    WHERE group_id = ? AND date >= ? AND date < ?
                ''', (group_id, start_date, end_date))
                result = {row[0]: "has_homework" for row in cursor.fetchall()}
            
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения дат ДЗ: {e}")
            return {}
    
    def add_homework(self, group_id, date, subject, text, files, created_by):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO homework (group_id, date, subject, text, files, created_by) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (group_id, date, subject, text, files, created_by))
            homework_id = cursor.lastrowid
            conn.commit()
            conn.close()
            logger.info(f"Добавлено ДЗ: {subject} на {date}")
            return homework_id
        except Exception as e:
            logger.error(f"Ошибка при добавлении ДЗ: {e}")
            return None
    
    def delete_homework(self, homework_id, user_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.is_admin FROM users u
                JOIN homework h ON u.group_id = (SELECT group_id FROM homework WHERE id = ?)
                WHERE u.user_id = ?
            ''', (homework_id, user_id))
            result = cursor.fetchone()
            
            if result and result[0]:
                cursor.execute('SELECT files FROM homework WHERE id = ?', (homework_id,))
                files_result = cursor.fetchone()
                
                cursor.execute('DELETE FROM homework_completion WHERE homework_id = ?', (homework_id,))
                cursor.execute('DELETE FROM homework WHERE id = ?', (homework_id,))
                conn.commit()
                logger.info(f"Удалено ДЗ с ID: {homework_id}")
                
                files_info = files_result[0] if files_result and files_result[0] else None
                if files_info:
                    logger.info(f"Файлы, связанные с удаленным ДЗ: {files_info}")
                
                conn.close()
                return True
            
            conn.close()
            return False
        except Exception as e:
            logger.error(f"Ошибка удаления ДЗ: {e}")
            return False
    
    def toggle_homework_completion(self, user_id, homework_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT id FROM homework_completion WHERE user_id = ? AND homework_id = ?',
                         (user_id, homework_id))
            result = cursor.fetchone()
            
            if result:
                cursor.execute('DELETE FROM homework_completion WHERE user_id = ? AND homework_id = ?',
                             (user_id, homework_id))
                status = False
            else:
                cursor.execute('INSERT INTO homework_completion (user_id, homework_id) VALUES (?, ?)',
                             (user_id, homework_id))
                status = True
            
            conn.commit()
            conn.close()
            logger.info(f"Статус выполнения ДЗ {homework_id} для пользователя {user_id}: {status}")
            return status
        except Exception as e:
            logger.error(f"Ошибка переключения статуса выполнения: {e}")
            return None
    
    def get_group_members(self, group_id):
        """ИСПРАВЛЕНО: убран ROW_NUMBER, используется стабильная сортировка"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, is_admin, joined_at
                FROM users 
                WHERE group_id = ? 
                ORDER BY user_id ASC
            ''', (group_id,))
            result = cursor.fetchall()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения участников группы: {e}")
            return []
    
    def remove_user_from_group(self, user_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM homework_completion WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            logger.info(f"Пользователь {user_id} удален из группы")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя: {e}")
            return False
    
    def toggle_admin_status(self, user_id):
        """ИСПРАВЛЕНО: добавлена отладочная информация"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # ОТЛАДКА: проверяем существование пользователя
            cursor.execute('SELECT user_id, username, is_admin FROM users WHERE user_id = ?', (user_id,))
            user_data = cursor.fetchone()
            
            if user_data:
                current_user_id, username, current_status = user_data
                new_status = 0 if current_status else 1
                
                logger.info(f"Переключение статуса админа: user_id={current_user_id}, username={username}, {current_status} -> {new_status}")
                
                cursor.execute('UPDATE users SET is_admin = ? WHERE user_id = ?', (new_status, user_id))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"✅ Статус админа для пользователя {user_id} ({username}) успешно изменен на {new_status}")
                    conn.close()
                    return True
                else:
                    logger.error(f"❌ Не удалось обновить статус для пользователя {user_id}")
                    conn.close()
                    return False
            else:
                logger.error(f"❌ Пользователь с ID {user_id} не найден в базе данных")
                conn.close()
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка переключения статуса админа для user_id {user_id}: {e}")
            return False
    
    def get_user_info(self, user_id):
        """НОВАЯ ФУНКЦИЯ: получить информацию о пользователе"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, username, is_admin FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
            return None

# Класс для работы с личной базой данных
class PersonalHomeworkManager:
    def __init__(self, db_path="personal_homework.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS personal_homework (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    text TEXT NOT NULL,
                    files TEXT,
                    completed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("База данных личных ДЗ инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД личных ДЗ: {e}")
    
    def get_personal_homework_for_date(self, user_id, date):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, subject, text, files, completed
                FROM personal_homework 
                WHERE user_id = ? AND date = ?
                ORDER BY subject
            ''', (user_id, date))
            result = cursor.fetchall()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения личных ДЗ: {e}")
            return []
    
    def get_personal_homework_dates_for_month(self, user_id, year, month):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            start_date = f"{year}-{month:02d}-01"
            if month == 12:
                end_date = f"{year + 1}-01-01"
            else:
                end_date = f"{year}-{month + 1:02d}-01"
            
            cursor.execute('''
                SELECT date
                FROM personal_homework
                WHERE user_id = ? AND date >= ? AND date < ?
                GROUP BY date
            ''', (user_id, start_date, end_date))
            
            # Просто возвращаем даты с заметками, без учета статуса выполнения
            result = {row[0]: "has_personal" for row in cursor.fetchall()}
            
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения дат личных ДЗ: {e}")
            return {}
    
    def add_personal_homework(self, user_id, date, subject, text, files):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO personal_homework (user_id, date, subject, text, files) 
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, date, subject, text, files))
            homework_id = cursor.lastrowid
            conn.commit()
            conn.close()
            logger.info(f"Добавлено личное ДЗ: {subject} на {date} для пользователя {user_id}")
            return homework_id
        except Exception as e:
            logger.error(f"Ошибка при добавлении личного ДЗ: {e}")
            return None
    
    def delete_personal_homework(self, homework_id, user_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT files FROM personal_homework WHERE id = ? AND user_id = ?', (homework_id, user_id))
            files_result = cursor.fetchone()
            
            cursor.execute('DELETE FROM personal_homework WHERE id = ? AND user_id = ?', (homework_id, user_id))
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            if success:
                logger.info(f"Удалено личное ДЗ с ID: {homework_id}")
                files_info = files_result[0] if files_result and files_result[0] else None
                if files_info:
                    logger.info(f"Файлы, связанные с удаленным личным ДЗ: {files_info}")
            
            return success
        except Exception as e:
            logger.error(f"Ошибка удаления личного ДЗ: {e}")
            return False
    
    def toggle_personal_homework_completion(self, user_id, homework_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT completed FROM personal_homework WHERE id = ? AND user_id = ?',
                         (homework_id, user_id))
            result = cursor.fetchone()
            
            if result:
                current_status = result[0]
                new_status = 0 if current_status else 1
                cursor.execute('UPDATE personal_homework SET completed = ? WHERE id = ? AND user_id = ?',
                             (new_status, homework_id, user_id))
                conn.commit()
                logger.info(f"Статус выполнения личного ДЗ {homework_id} для пользователя {user_id}: {bool(new_status)}")
                conn.close()
                return bool(new_status)
            
            conn.close()
            return None
        except Exception as e:
            logger.error(f"Ошибка переключения статуса выполнения личного ДЗ: {e}")
            return None

# Инициализируем менеджеры баз данных
db = DatabaseManager()
personal_db = PersonalHomeworkManager()

# Глобальные переменные для сохранения контекста
homework_context = {}

# ФУНКЦИИ ДЛЯ СОЗДАНИЯ КЛАВИАТУР

def get_main_reply_keyboard(is_admin=False):
    """Создать reply клавиатуру главного меню - ФИКСИРОВАННАЯ"""
    keyboard = []
    
    # Первый ряд: Посмотреть ДЗ, Добавить ДЗ
    first_row = [KeyboardButton(text=f"{EMOJI['view_homework']} Просмотреть ДЗ")]
    if is_admin:
        first_row.append(KeyboardButton(text=f"{EMOJI['add_homework']} Добавить ДЗ"))
    keyboard.append(first_row)
    
    # Второй ряд: Личные заметки, Управление участниками  
    second_row = [KeyboardButton(text="📝 Личные заметки")]
    if is_admin:
        second_row.append(KeyboardButton(text=f"{EMOJI['manage_users']} Управление участниками"))
    keyboard.append(second_row)
    
    # Третий ряд: Главное меню и Выйти из группы
    keyboard.append([
        KeyboardButton(text="🏠 Главное меню"),
        KeyboardButton(text=f"{EMOJI['leave_group']} Выйти из группы")
    ])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_personal_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="👀 Просмотреть заметки", callback_data="view_personal")],
        [InlineKeyboardButton(text="➕ Добавить заметку", callback_data="add_personal")],
        [InlineKeyboardButton(text=f"{EMOJI['back']} В главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_homework_files_keyboard():
    """Создать клавиатуру для выбора файлов к ДЗ - БЕЗ reply кнопок"""
    keyboard = [
        [InlineKeyboardButton(text="📎 Прикрепить файлы", callback_data="attach_files")],
        [InlineKeyboardButton(text="✅ Готово без файлов", callback_data="done_without_files")],
        [InlineKeyboardButton(text=f"{EMOJI['back']} Назад", callback_data="back_from_files")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_calendar_keyboard(year, month, mode="view", group_id=None, user_id=None):
    """Создать календарную клавиатуру с индикаторами ДЗ"""
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)
    
    homework_dates = {}
    personal_dates = {}
    
    if group_id and mode in ["view", "add"]:
        if mode == "view" and user_id:
            homework_dates = db.get_homework_dates_for_month(group_id, year, month, user_id)
        elif mode == "add":
            homework_dates = db.get_homework_dates_for_month(group_id, year, month)
    
    if user_id and mode in ["view_personal", "add_personal"]:
        personal_dates = personal_db.get_personal_homework_dates_for_month(user_id, year, month)
    
    keyboard = []
    
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    keyboard.append([
        InlineKeyboardButton(text=EMOJI['left_arrow'], callback_data=f"cal_nav_{prev_year}_{prev_month}_{mode}"),
        InlineKeyboardButton(text=f"{CALENDAR_MONTHS_RU[month-1]} {year}", callback_data="ignore"),
        InlineKeyboardButton(text=EMOJI['right_arrow'], callback_data=f"cal_nav_{next_year}_{next_month}_{mode}")
    ])
    
    keyboard.append([InlineKeyboardButton(text=day, callback_data="ignore") for day in CALENDAR_WEEKDAYS_RU])
    
    for week in month_days:
        week_buttons = []
        for day in week:
            if day == 0:
                week_buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                day_text = str(day)
                
                if mode == "view" and user_id and date_str in homework_dates:
                    status = homework_dates[date_str]
                    if status == "complete":
                        day_text = f"{day}🟢"
                    elif status == "partial":
                        day_text = f"{day}🟡"
                    else:
                        day_text = f"{day}🔵"
                elif mode == "add" and date_str in homework_dates:
                    day_text = f"{day}🔵"
                elif mode in ["view_personal", "add_personal"] and date_str in personal_dates:
                    day_text = f"{day}💙"
                
                if mode == "add":
                    callback_prefix = "add_hw_date"
                elif mode == "add_personal":
                    callback_prefix = "add_personal_date"
                elif mode == "view_personal":
                    callback_prefix = "personal_date"
                else:
                    callback_prefix = "date"
                
                week_buttons.append(InlineKeyboardButton(text=day_text, callback_data=f"{callback_prefix}_{date_str}"))
        keyboard.append(week_buttons)
    
    if mode in ["view_personal", "add_personal"]:
        keyboard.append([InlineKeyboardButton(text=f"{EMOJI['back']} К личным заметкам", callback_data="personal_homework")])
    else:
        keyboard.append([InlineKeyboardButton(text=f"{EMOJI['back']} Назад", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_homework_actions_keyboard(user_id, is_admin=False, is_personal=False):
    keyboard = []
    
    keyboard.append([
        InlineKeyboardButton(text="✅ Отметить выполненным", callback_data="mark_completed" if not is_personal else "mark_personal_completed"),
    ])
    
    if is_admin and not is_personal:
        keyboard.append([
            InlineKeyboardButton(text="🗑 Удалить задания", callback_data="delete_homework")
        ])
    elif is_personal:
        keyboard.append([
            InlineKeyboardButton(text="🗑 Удалить заметки", callback_data="delete_personal")
        ])
    
    back_callback = "view_personal" if is_personal else "view_homework"
    keyboard.append([
        InlineKeyboardButton(text=f"{EMOJI['back']} К календарю", callback_data=back_callback)
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_homework_selection_keyboard(homework_list, mode="complete", is_personal=False):
    keyboard = []
    
    for hw_id, subject, text, files, completed in homework_list:
        if mode == "complete":
            status_text = "🔲" if completed else "⬜"
            callback_prefix = "toggle_personal_hw" if is_personal else "toggle_hw"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_text} {subject}",
                    callback_data=f"{callback_prefix}_{hw_id}"
                )
            ])
        elif mode == "delete":
            callback_prefix = "delete_personal_hw" if is_personal else "delete_hw"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🗑 {subject}",
                    callback_data=f"{callback_prefix}_{hw_id}"
                )
            ])
    
    back_callback = "back_to_personal_actions" if is_personal else "back_to_actions"
    keyboard.append([InlineKeyboardButton(text=f"{EMOJI['back']} Назад", callback_data=back_callback)])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_confirmation_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(text=f"{EMOJI['confirm']} Да, выйти", callback_data="confirm_leave"),
            InlineKeyboardButton(text=f"{EMOJI['cancel']} Отмена", callback_data="cancel_leave")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def count_files(files_string):
    if not files_string:
        return 0
    return len(files_string.split("|"))

async def send_homework_files(message: Message, files_string: str, subject_name: str):
    if not files_string:
        return
    
    try:
        files = files_string.split("|")
        media_group = []
        
        for i, file_info in enumerate(files[:10]):
            if file_info.startswith("photo:"):
                file_id = file_info.split(":", 1)[1]
                caption = f"📚 {subject_name}" if i == 0 else ""
                media_group.append(InputMediaPhoto(media=file_id, caption=caption))
        
        if media_group:
            await message.answer_media_group(media_group)
        
        for file_info in files:
            if file_info.startswith("document:"):
                parts = file_info.split(":", 2)
                file_id = parts[1]
                await message.answer_document(file_id, caption=f"📄 {subject_name}")
                
    except Exception as e:
        logger.error(f"Ошибка отправки файлов: {e}")
        await message.answer("❌ Ошибка при загрузке прикрепленных файлов")

# ОСНОВНЫЕ ОБРАБОТЧИКИ
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    try:
        await state.clear()
        user_group = db.get_user_group(message.from_user.id)
        
        if user_group:
            group_id, is_admin = user_group
            group_name = db.get_group_name(group_id)
            
            welcome_text = f"🎉 <b>С возвращением!</b>\n\n📋 Вы находитесь в группе: <b>«{group_name}»</b>\n📝 Также доступны личные заметки\n🚀 Выберите действие в меню ниже"
            
            await message.answer(
                welcome_text,
                reply_markup=get_main_reply_keyboard(bool(is_admin))
            )
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎓 Присоединиться к группе", callback_data="join_group")
            ]])
            await message.answer("🎓 <b>Добро пожаловать в HomeworkBot!</b>\n\n📚 Ваш персональный помощник для управления домашними заданиями\n📝 Поддерживает как групповые, так и личные заметки\n\n✨ <i>Для начала работы присоединитесь к группе</i>", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка в start_handler: {e}")
        await message.answer(MESSAGES["error_occurred"])

# REPLY КНОПКИ
@dp.message(F.text == "🏠 Главное меню")
async def main_menu_reply_handler(message: Message, state: FSMContext):
    """ИСПРАВЛЕНО: обновляем reply клавиатуру и убираем все inline кнопки"""
    try:
        await state.clear()
        user_group = db.get_user_group(message.from_user.id)
        if user_group:
            group_id, is_admin = user_group
            group_name = db.get_group_name(group_id)
            
            main_menu_text = f"🏠 <b>Главное меню</b>\n\n📊 Группа: <b>«{group_name}»</b>\n📝 Личные заметки: <b>Доступны</b>\n\n📌 Используйте кнопки ниже для навигации"
            
            # ИСПРАВЛЕНО: обновляем reply клавиатуру при возврате в главное меню
            await message.answer(main_menu_text, reply_markup=get_main_reply_keyboard(bool(is_admin)))
    except Exception as e:
        logger.error(f"Ошибка в main_menu_reply_handler: {e}")
        await message.answer(MESSAGES["error_occurred"])

@dp.message(F.text.startswith(f"{EMOJI['view_homework']} Просмотреть ДЗ"))
async def view_homework_reply_handler(message: Message):
    try:
        user_group = db.get_user_group(message.from_user.id)
        if user_group:
            group_id, is_admin = user_group
            now = datetime.now()
            keyboard = get_calendar_keyboard(now.year, now.month, "view", group_id, message.from_user.id)
            await message.answer(
                MESSAGES["select_date_view"],
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Ошибка в view_homework_reply_handler: {e}")
        await message.answer(MESSAGES["error_occurred"])

@dp.message(F.text == "📝 Личные заметки")
async def personal_homework_reply_handler(message: Message):
    try:
        text = "📝 <b>Личные заметки</b>\n\n💡 Здесь вы можете создавать заметки только для себя\n🔒 Никто другой не сможет их увидеть\n\n📌 Выберите действие:"
        keyboard = get_personal_menu_keyboard()
        await message.answer(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка в personal_homework_reply_handler: {e}")
        await message.answer(MESSAGES["error_occurred"])

@dp.message(F.text.startswith(f"{EMOJI['add_homework']} Добавить ДЗ"))
async def add_homework_reply_handler(message: Message):
    try:
        user_group = db.get_user_group(message.from_user.id)
        if user_group and user_group[1]:
            now = datetime.now()
            keyboard = get_calendar_keyboard(now.year, now.month, "add", user_group[0])
            await message.answer(
                MESSAGES["select_date_add"],
                reply_markup=keyboard
            )
        else:
            await message.answer(MESSAGES["no_add_homework_rights"])
    except Exception as e:
        logger.error(f"Ошибка в add_homework_reply_handler: {e}")
        await message.answer(MESSAGES["error_occurred"])

@dp.message(F.text.startswith(f"{EMOJI['manage_users']} Управление участниками"))
async def manage_users_reply_handler(message: Message):
    """ИСПРАВЛЕНО: новая логика отображения участников"""
    try:
        user_group = db.get_user_group(message.from_user.id)
        if user_group and user_group[1]:
            group_id, _ = user_group
            members = db.get_group_members(group_id)
            
            if not members:
                await message.answer("👥 <b>Участники группы</b>\n\n❌ Участники не найдены")
                return
            
            text = "👥 <b>Участники группы</b>\n\n📊 <b>Состав группы:</b>\n\n"
            keyboard = []
            
            # ИСПРАВЛЕНО: не используем member_number из БД, создаем свой счетчик
            for index, (user_id, username, is_admin, joined_at) in enumerate(members, 1):
                status_text = "👑 <b>Администратор</b>" if is_admin else "👤 <b>Участник</b>"
                user_display = username or f"ID: {user_id}"
                text += f"👤 <b>#{index} {user_display}</b>\n{status_text}\n\n"
                
                # Не показываем кнопки управления для самого себя
                if user_id != message.from_user.id:
                    admin_text = f"Снять права #{index}" if is_admin else f"Дать права #{index}"
                    keyboard.append([
                        InlineKeyboardButton(text=f"{EMOJI['change']} {admin_text}",
                                           callback_data=f"toggle_admin_{user_id}"),
                        InlineKeyboardButton(text=f"{EMOJI['remove']} Исключить #{index}",
                                           callback_data=f"remove_user_{user_id}")
                    ])
            
            keyboard.append([InlineKeyboardButton(text=f"{EMOJI['back']} В главное меню", callback_data="main_menu")])
            
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        else:
            await message.answer(MESSAGES["no_manage_users_rights"])
    except Exception as e:
        logger.error(f"Ошибка в manage_users_reply_handler: {e}")
        await message.answer(MESSAGES["error_occurred"])

@dp.message(F.text.startswith(f"{EMOJI['leave_group']} Выйти из группы"))
async def leave_group_reply_handler(message: Message):
    try:
        await message.answer(
            MESSAGES["confirm_leave_group"],
            reply_markup=get_confirmation_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в leave_group_reply_handler: {e}")
        await message.answer(MESSAGES["error_occurred"])

# ОБРАБОТЧИКИ ФАЙЛОВ
@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    try:
        current_state = await state.get_state()
        if current_state in [GroupStates.waiting_homework_files, GroupStates.waiting_personal_files]:
            data = await state.get_data()
            files = data.get('homework_files', [])
            files.append(f"photo:{message.photo[-1].file_id}")
            await state.update_data(homework_files=files)
            
            await message.answer(
                f"📷 Фото добавлено!\n\n"
                f"📎 Всего файлов: {len(files)}\n"
                f"➕ Можете прикрепить еще файлы или нажать 'Готово'"
            )
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await message.answer("❌ Ошибка при обработке фото")

@dp.message(F.document)
async def handle_document(message: Message, state: FSMContext):
    try:
        current_state = await state.get_state()
        if current_state in [GroupStates.waiting_homework_files, GroupStates.waiting_personal_files]:
            data = await state.get_data()
            files = data.get('homework_files', [])
            files.append(f"document:{message.document.file_id}:{message.document.file_name}")
            await state.update_data(homework_files=files)
            
            await message.answer(
                f"📄 Файл '{message.document.file_name}' добавлен!\n\n"
                f"📎 Всего файлов: {len(files)}\n"
                f"➕ Можете прикрепить еще файлы или нажать 'Готово'"
            )
    except Exception as e:
        logger.error(f"Ошибка обработки документа: {e}")
        await message.answer("❌ Ошибка при обработке файла")

# НОВЫЕ ОБРАБОТЧИКИ INLINE КНОПОК ДЛЯ ФАЙЛОВ
@dp.callback_query(F.data == "attach_files")
async def attach_files_callback_handler(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "📎 <b>Прикрепление файлов</b>\n\n"
            "📷 Отправьте фото или файлы для задания\n"
            "📝 После отправки всех файлов нажмите 'Готово с файлами'\n\n"
            "💡 Можно отправить несколько файлов подряд",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Готово с файлами", callback_data="done_with_files")],
                [InlineKeyboardButton(text=f"{EMOJI['back']} Назад", callback_data="back_from_files")]
            ])
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в attach_files_callback_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "done_without_files")
async def done_without_files_callback_handler(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_state_name = await state.get_state()
        
        if current_state_name == GroupStates.waiting_personal_files:
            success = personal_db.add_personal_homework(
                callback.from_user.id,
                data['homework_date'],
                data['homework_subject'],
                data['homework_text'],
                None
            )
            
            if success:
                date_obj = datetime.strptime(data['homework_date'], "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                
                user_group = db.get_user_group(callback.from_user.id)
                is_admin = user_group[1] if user_group else False
                
                await callback.message.edit_text(
                    f"✅ <b>Личная заметка добавлена!</b>\n\n"
                    f"📅 <b>Дата:</b> {formatted_date}\n"
                    f"📚 <b>Предмет:</b> {data['homework_subject']}\n"
                    f"📖 <b>Задание:</b> {data['homework_text']}"
                )
                
                # ИСПРАВЛЕНО: обновляем reply клавиатуру
                await callback.message.answer(
                    "🏠 Возвращение в главное меню",
                    reply_markup=get_main_reply_keyboard(bool(is_admin))
                )
        else:
            user_group = db.get_user_group(callback.from_user.id)
            if user_group:
                group_id, is_admin = user_group
                success = db.add_homework(
                    group_id,
                    data['homework_date'],
                    data['homework_subject'],
                    data['homework_text'],
                    None,
                    callback.from_user.id
                )
                
                if success:
                    date_obj = datetime.strptime(data['homework_date'], "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m.%Y")
                    
                    await callback.message.edit_text(
                        MESSAGES["homework_added"].format(
                            formatted_date,
                            data['homework_subject'],
                            data['homework_text']
                        )
                    )
                    
                    # ИСПРАВЛЕНО: обновляем reply клавиатуру
                    await callback.message.answer(
                        "🏠 Возвращение в главное меню",
                        reply_markup=get_main_reply_keyboard(bool(is_admin))
                    )
                else:
                    await callback.answer(MESSAGES["error_occurred"], show_alert=True)
        
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в done_without_files_callback_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)
        await state.clear()

@dp.callback_query(F.data == "done_with_files")
async def done_with_files_callback_handler(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_state_name = await state.get_state()
        files = data.get('homework_files', [])
        files_json = "|".join(files) if files else None
        
        if current_state_name == GroupStates.waiting_personal_files:
            success = personal_db.add_personal_homework(
                callback.from_user.id,
                data['homework_date'],
                data['homework_subject'],
                data['homework_text'],
                files_json
            )
            
            if success:
                date_obj = datetime.strptime(data['homework_date'], "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                files_text = f"\n📎 Файлов прикреплено: {len(files)}" if files else ""
                
                user_group = db.get_user_group(callback.from_user.id)
                is_admin = user_group[1] if user_group else False
                
                await callback.message.edit_text(
                    f"✅ <b>Личная заметка добавлена!</b>\n\n"
                    f"📅 <b>Дата:</b> {formatted_date}\n"
                    f"📚 <b>Предмет:</b> {data['homework_subject']}\n"
                    f"📖 <b>Задание:</b> {data['homework_text']}{files_text}"
                )
                
                # ИСПРАВЛЕНО: обновляем reply клавиатуру
                await callback.message.answer(
                    "🏠 Возвращение в главное меню",
                    reply_markup=get_main_reply_keyboard(bool(is_admin))
                )
        else:
            user_group = db.get_user_group(callback.from_user.id)
            if user_group:
                group_id, is_admin = user_group
                success = db.add_homework(
                    group_id,
                    data['homework_date'],
                    data['homework_subject'],
                    data['homework_text'],
                    files_json,
                    callback.from_user.id
                )
                
                if success:
                    date_obj = datetime.strptime(data['homework_date'], "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m.%Y")
                    files_text = f"\n📎 Файлов прикреплено: {len(files)}" if files else ""
                    
                    await callback.message.edit_text(
                        MESSAGES["homework_added"].format(
                            formatted_date,
                            data['homework_subject'],
                            data['homework_text']
                        ) + files_text
                    )
                    
                    # ИСПРАВЛЕНО: обновляем reply клавиатуру
                    await callback.message.answer(
                        "🏠 Возвращение в главное меню",
                        reply_markup=get_main_reply_keyboard(bool(is_admin))
                    )
                else:
                    await callback.answer(MESSAGES["error_occurred"], show_alert=True)
        
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в done_with_files_callback_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)
        await state.clear()

@dp.callback_query(F.data == "back_from_files")
async def back_from_files_callback_handler(callback: CallbackQuery, state: FSMContext):
    try:
        current_state_name = await state.get_state()
        
        if current_state_name == GroupStates.waiting_personal_files:
            await callback.message.edit_text("📖 <b>Введите текст личной заметки:</b>")
            await state.set_state(GroupStates.waiting_personal_text)
        else:
            await callback.message.edit_text(MESSAGES["enter_homework_text"])
            await state.set_state(GroupStates.waiting_homework_text)
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в back_from_files_callback_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

# CALLBACK ОБРАБОТЧИКИ - ВСЕ ВОССТАНОВЛЕНЫ!

@dp.callback_query(F.data == "join_group")
async def join_group_handler(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_text(MESSAGES["enter_group_name"])
        await state.set_state(GroupStates.waiting_group_name)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в join_group_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery, state: FSMContext):
    """ИСПРАВЛЕНО: обновляем reply клавиатуру и убираем все inline кнопки"""
    try:
        await state.clear()
        user_group = db.get_user_group(callback.from_user.id)
        if user_group:
            group_id, is_admin = user_group
            group_name = db.get_group_name(group_id)
            
            main_menu_text = f"🏠 <b>Главное меню</b>\n\n📊 Группа: <b>«{group_name}»</b>\n📝 Личные заметки: <b>Доступны</b>\n\n📌 Используйте кнопки ниже для навигации"
            
            await callback.message.edit_text(main_menu_text)
            
            # ИСПРАВЛЕНО: обновляем reply клавиатуру при возврате из inline меню
            await callback.message.answer(
                "🔄 Клавиатура обновлена",
                reply_markup=get_main_reply_keyboard(bool(is_admin))
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в main_menu_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "view_homework")
async def view_homework_handler(callback: CallbackQuery):
    try:
        user_group = db.get_user_group(callback.from_user.id)
        if user_group:
            group_id, is_admin = user_group
            now = datetime.now()
            keyboard = get_calendar_keyboard(now.year, now.month, "view", group_id, callback.from_user.id)
            await callback.message.edit_text(
                MESSAGES["select_date_view"],
                reply_markup=keyboard
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в view_homework_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

# ЛИЧНЫЕ ЗАМЕТКИ - CALLBACK ОБРАБОТЧИКИ
@dp.callback_query(F.data == "personal_homework")
async def personal_homework_handler(callback: CallbackQuery):
    try:
        text = "📝 <b>Личные заметки</b>\n\n💡 Здесь вы можете создавать заметки только для себя\n🔒 Никто другой не сможет их увидеть\n\n📌 Выберите действие:"
        keyboard = get_personal_menu_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в personal_homework_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "view_personal")
async def view_personal_handler(callback: CallbackQuery):
    try:
        now = datetime.now()
        keyboard = get_calendar_keyboard(now.year, now.month, "view_personal", None, callback.from_user.id)
        await callback.message.edit_text(
            "📅 <b>Выберите дату для просмотра личных заметок:</b>\n\n"
            "💙 - есть заметки на эту дату",
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в view_personal_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "add_personal")
async def add_personal_handler(callback: CallbackQuery):
    try:
        now = datetime.now()
        keyboard = get_calendar_keyboard(now.year, now.month, "add_personal", None, callback.from_user.id)
        await callback.message.edit_text(
            "📅 <b>Выберите дату для личной заметки:</b>\n\n"
            "💙 - есть заметки на эту дату",
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в add_personal_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

# ВОССТАНОВЛЕННЫЕ ОБРАБОТЧИКИ ДАТ - ВОТ ОНИ!

@dp.callback_query(F.data.startswith("date_"))
async def date_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: обработчик нажатия на дату для просмотра ДЗ"""
    try:
        date_str = callback.data.split("_", 1)[1]
        user_group = db.get_user_group(callback.from_user.id)
        
        if user_group:
            group_id, is_admin = user_group
            homework = db.get_homework_for_date(group_id, date_str, callback.from_user.id)
            
            homework_context[callback.from_user.id] = {
                'date': date_str,
                'homework': homework,
                'is_admin': is_admin,
                'is_personal': False
            }
            
            if homework:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                
                text = f"📋 <b>Домашние задания на {formatted_date}</b>\n\n"
                
                for hw_id, subject, hw_text, files, completed in homework:
                    status = "✅ Выполнено" if completed else "⬜ Не выполнено"
                    text += f"📚 <b>{subject}</b>\n"
                    
                    files_count = count_files(files)
                    if files_count > 0:
                        text += f"📎 Файлов: {files_count}\n"
                    
                    text += f"📖 <i>{hw_text}</i>\n"
                    text += f"🔲 {status}\n\n"
                
                keyboard = get_homework_actions_keyboard(callback.from_user.id, bool(is_admin), False)
                await callback.message.edit_text(text, reply_markup=keyboard)
                
                for hw_id, subject, hw_text, files, completed in homework:
                    if files:
                        await send_homework_files(callback.message, files, subject)
                
            else:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                text = f"😌 <b>Свободный день!</b>\n\n🎯 На <b>{formatted_date}</b> домашних заданий нет\n\n🌟 <i>Отличное время для отдыха или повторения пройденного материала</i>"
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=f"{EMOJI['back']} К календарю", callback_data="view_homework")
                ]])
                await callback.message.edit_text(text, reply_markup=keyboard)
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в date_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data.startswith("personal_date_"))
async def personal_date_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: обработчик нажатия на дату для просмотра личных заметок"""
    try:
        date_str = callback.data.split("_", 2)[2]
        homework = personal_db.get_personal_homework_for_date(callback.from_user.id, date_str)
        
        homework_context[callback.from_user.id] = {
            'date': date_str,
            'homework': homework,
            'is_admin': False,
            'is_personal': True
        }
        
        if homework:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            
            text = f"📝 <b>Личные заметки на {formatted_date}</b>\n\n"
            
            for hw_id, subject, hw_text, files, completed in homework:
                status = "✅ Выполнено" if completed else "⬜ Не выполнено"
                text += f"📚 <b>{subject}</b>\n"
                
                files_count = count_files(files)
                if files_count > 0:
                    text += f"📎 Файлов: {files_count}\n"
                
                text += f"📖 <i>{hw_text}</i>\n"
                text += f"🔲 {status}\n\n"
            
            keyboard = get_homework_actions_keyboard(callback.from_user.id, False, True)
            await callback.message.edit_text(text, reply_markup=keyboard)
            
            for hw_id, subject, hw_text, files, completed in homework:
                if files:
                    await send_homework_files(callback.message, files, subject)
            
        else:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            text = f"📝 <b>Свободный день!</b>\n\n🎯 На <b>{formatted_date}</b> личных заметок нет\n\n💡 <i>Можете добавить новую заметку</i>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить заметку", callback_data=f"add_personal_date_{date_str}")],
                [InlineKeyboardButton(text=f"{EMOJI['back']} К календарю", callback_data="view_personal")]
            ])
            await callback.message.edit_text(text, reply_markup=keyboard)
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в personal_date_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data.startswith("add_personal_date_"))
async def add_personal_date_handler(callback: CallbackQuery, state: FSMContext):
    """ВОССТАНОВЛЕН: обработчик нажатия на дату для добавления личной заметки"""
    try:
        date_str = callback.data.split("_", 3)[3]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d.%m.%Y")
        
        await state.update_data(homework_date=date_str)
        await callback.message.edit_text(f"📚 <b>Введите предмет для заметки на {formatted_date}:</b>")
        await state.set_state(GroupStates.waiting_personal_subject)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в add_personal_date_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)
        await state.clear()

@dp.callback_query(F.data.startswith("add_hw_date_"))
async def add_homework_date_handler(callback: CallbackQuery, state: FSMContext):
    """ВОССТАНОВЛЕН: обработчик нажатия на дату для добавления ДЗ"""
    try:
        date_str = callback.data.split("_", 3)[3]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d.%m.%Y")
        
        await state.update_data(homework_date=date_str)
        await callback.message.edit_text(MESSAGES["enter_subject"].format(formatted_date))
        await state.set_state(GroupStates.waiting_homework_subject)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в add_homework_date_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)
        await state.clear()

# НАВИГАЦИЯ ПО КАЛЕНДАРЮ - ВОССТАНОВЛЕНА
@dp.callback_query(F.data.startswith("cal_nav_"))
async def calendar_nav_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: навигация по месяцам календаря"""
    try:
        parts = callback.data.split("_")
        year, month = int(parts[2]), int(parts[3])
        mode = parts[4] if len(parts) > 4 else "view"
        
        user_group = db.get_user_group(callback.from_user.id)
        if user_group and mode in ["view", "add"]:
            group_id = user_group[0]
            user_id = callback.from_user.id if mode == "view" else None
            keyboard = get_calendar_keyboard(year, month, mode, group_id, user_id)
        elif mode in ["view_personal", "add_personal"]:
            keyboard = get_calendar_keyboard(year, month, mode, None, callback.from_user.id)
        else:
            keyboard = get_calendar_keyboard(year, month, mode)
        
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в calendar_nav_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

# ДЕЙСТВИЯ С ДЗ - ВОССТАНОВЛЕНЫ
@dp.callback_query(F.data == "mark_completed")
async def mark_completed_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: отметить ДЗ как выполненное"""
    try:
        context = homework_context.get(callback.from_user.id)
        if context and context.get('homework') and not context.get('is_personal', False):
            text = "✅ <b>Отметить выполненным</b>\n\nВыберите задания для изменения статуса:"
            keyboard = get_homework_selection_keyboard(context['homework'], "complete", False)
            await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в mark_completed_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "delete_homework")
async def delete_homework_action_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: удалить ДЗ"""
    try:
        context = homework_context.get(callback.from_user.id)
        if context and context.get('homework') and not context.get('is_personal', False):
            text = "🗑 <b>Удалить задания</b>\n\nВыберите задания для удаления:"
            keyboard = get_homework_selection_keyboard(context['homework'], "delete", False)
            await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в delete_homework_action_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "back_to_actions")
async def back_to_actions_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: вернуться к действиям с ДЗ"""
    try:
        context = homework_context.get(callback.from_user.id)
        if context and context.get('date') and not context.get('is_personal', False):
            user_group = db.get_user_group(callback.from_user.id)
            if user_group:
                group_id, is_admin = user_group
                homework = db.get_homework_for_date(group_id, context['date'], callback.from_user.id)
                
                homework_context[callback.from_user.id] = {
                    'date': context['date'],
                    'homework': homework,
                    'is_admin': is_admin,
                    'is_personal': False
                }
                
                if homework:
                    date_obj = datetime.strptime(context['date'], "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m.%Y")
                    
                    text = f"📋 <b>Домашние задания на {formatted_date}</b>\n\n"
                    
                    for hw_id, subject, hw_text, files, completed in homework:
                        status = "✅ Выполнено" if completed else "⬜ Не выполнено"
                        text += f"📚 <b>{subject}</b>\n"
                        
                        files_count = count_files(files)
                        if files_count > 0:
                            text += f"📎 Файлов: {files_count}\n"
                        
                        text += f"📖 <i>{hw_text}</i>\n"
                        text += f"🔲 {status}\n\n"
                    
                    keyboard = get_homework_actions_keyboard(callback.from_user.id, bool(is_admin), False)
                    await callback.message.edit_text(text, reply_markup=keyboard)
                else:
                    await view_homework_handler(callback)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в back_to_actions_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data.startswith("toggle_hw_"))
async def toggle_homework_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: переключить статус выполнения ДЗ"""
    try:
        homework_id = int(callback.data.split("_")[2])
        status = db.toggle_homework_completion(callback.from_user.id, homework_id)
        
        if status is not None:
            status_text = "выполненным" if status else "невыполненным"
            await callback.answer(f"✅ Задание помечено как {status_text}!")
            
            await mark_completed_handler(callback)
        else:
            await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в toggle_homework_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data.startswith("delete_hw_"))
async def delete_homework_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: удалить конкретное ДЗ"""
    try:
        homework_id = int(callback.data.split("_")[2])
        success = db.delete_homework(homework_id, callback.from_user.id)
        
        if success:
            await callback.answer("🗑 Задание удалено!")
            
            context = homework_context.get(callback.from_user.id)
            if context and context.get('date'):
                user_group = db.get_user_group(callback.from_user.id)
                if user_group:
                    group_id, is_admin = user_group
                    homework = db.get_homework_for_date(group_id, context['date'], callback.from_user.id)
                    
                    homework_context[callback.from_user.id] = {
                        'date': context['date'],
                        'homework': homework,
                        'is_admin': is_admin,
                        'is_personal': False
                    }
                    
                    if homework:
                        await delete_homework_action_handler(callback)
                    else:
                        await view_homework_handler(callback)
        else:
            await callback.answer("❌ Ошибка при удалении или нет прав", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в delete_homework_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

# ДЕЙСТВИЯ С ЛИЧНЫМИ ЗАМЕТКАМИ - ВОССТАНОВЛЕНЫ
@dp.callback_query(F.data == "mark_personal_completed")
async def mark_personal_completed_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: отметить личную заметку как выполненную"""
    try:
        context = homework_context.get(callback.from_user.id)
        if context and context.get('homework') and context.get('is_personal'):
            text = "✅ <b>Отметить выполненным</b>\n\nВыберите заметки для изменения статуса:"
            keyboard = get_homework_selection_keyboard(context['homework'], "complete", True)
            await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в mark_personal_completed_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "delete_personal")
async def delete_personal_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: удалить личные заметки"""
    try:
        context = homework_context.get(callback.from_user.id)
        if context and context.get('homework') and context.get('is_personal'):
            text = "🗑 <b>Удалить заметки</b>\n\nВыберите заметки для удаления:"
            keyboard = get_homework_selection_keyboard(context['homework'], "delete", True)
            await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в delete_personal_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "back_to_personal_actions")
async def back_to_personal_actions_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: вернуться к действиям с личными заметками"""
    try:
        context = homework_context.get(callback.from_user.id)
        if context and context.get('date') and context.get('is_personal'):
            homework = personal_db.get_personal_homework_for_date(callback.from_user.id, context['date'])
            
            homework_context[callback.from_user.id] = {
                'date': context['date'],
                'homework': homework,
                'is_admin': False,
                'is_personal': True
            }
            
            if homework:
                date_obj = datetime.strptime(context['date'], "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                
                text = f"📝 <b>Личные заметки на {formatted_date}</b>\n\n"
                
                for hw_id, subject, hw_text, files, completed in homework:
                    status = "✅ Выполнено" if completed else "⬜ Не выполнено"
                    text += f"📚 <b>{subject}</b>\n"
                    
                    files_count = count_files(files)
                    if files_count > 0:
                        text += f"📎 Файлов: {files_count}\n"
                    
                    text += f"📖 <i>{hw_text}</i>\n"
                    text += f"🔲 {status}\n\n"
                
                keyboard = get_homework_actions_keyboard(callback.from_user.id, False, True)
                await callback.message.edit_text(text, reply_markup=keyboard)
            else:
                await view_personal_handler(callback)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в back_to_personal_actions_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data.startswith("toggle_personal_hw_"))
async def toggle_personal_homework_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: переключить статус выполнения личной заметки"""
    try:
        homework_id = int(callback.data.split("_")[3])
        status = personal_db.toggle_personal_homework_completion(callback.from_user.id, homework_id)
        
        if status is not None:
            status_text = "выполненной" if status else "невыполненной"
            await callback.answer(f"✅ Заметка помечена как {status_text}!")
            
            await mark_personal_completed_handler(callback)
        else:
            await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в toggle_personal_homework_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data.startswith("delete_personal_hw_"))
async def delete_personal_homework_handler(callback: CallbackQuery):
    """ВОССТАНОВЛЕН: удалить конкретную личную заметку"""
    try:
        homework_id = int(callback.data.split("_")[3])
        success = personal_db.delete_personal_homework(homework_id, callback.from_user.id)
        
        if success:
            await callback.answer("🗑 Заметка удалена!")
            
            context = homework_context.get(callback.from_user.id)
            if context and context.get('date'):
                homework = personal_db.get_personal_homework_for_date(callback.from_user.id, context['date'])
                
                homework_context[callback.from_user.id] = {
                    'date': context['date'],
                    'homework': homework,
                    'is_admin': False,
                    'is_personal': True
                }
                
                if homework:
                    await delete_personal_handler(callback)
                else:
                    await view_personal_handler(callback)
        else:
            await callback.answer("❌ Ошибка при удалении", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в delete_personal_homework_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

# УПРАВЛЕНИЕ УЧАСТНИКАМИ - ИСПРАВЛЕННЫЕ ОБРАБОТЧИКИ
@dp.callback_query(F.data == "manage_users")
async def manage_users_handler(callback: CallbackQuery):
    """ИСПРАВЛЕНО: такая же логика как в reply обработчике"""
    try:
        user_group = db.get_user_group(callback.from_user.id)
        if user_group and user_group[1]:
            group_id, _ = user_group
            members = db.get_group_members(group_id)
            
            if not members:
                await callback.message.edit_text("👥 <b>Участники группы</b>\n\n❌ Участники не найдены")
                await callback.answer()
                return
            
            text = "👥 <b>Участники группы</b>\n\n📊 <b>Состав группы:</b>\n\n"
            keyboard = []
            
            # ИСПРАВЛЕНО: не используем member_number из БД, создаем свой счетчик
            for index, (user_id, username, is_admin, joined_at) in enumerate(members, 1):
                status_text = "👑 <b>Администратор</b>" if is_admin else "👤 <b>Участник</b>"
                user_display = username or f"ID: {user_id}"
                text += f"👤 <b>#{index} {user_display}</b>\n{status_text}\n\n"
                
                if user_id != callback.from_user.id:
                    admin_text = f"Снять права #{index}" if is_admin else f"Дать права #{index}"
                    keyboard.append([
                        InlineKeyboardButton(text=f"{EMOJI['change']} {admin_text}",
                                           callback_data=f"toggle_admin_{user_id}"),
                        InlineKeyboardButton(text=f"{EMOJI['remove']} Исключить #{index}",
                                           callback_data=f"remove_user_{user_id}")
                    ])
            
            keyboard.append([InlineKeyboardButton(text=f"{EMOJI['back']} В главное меню", callback_data="main_menu")])
            
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        else:
            await callback.answer(MESSAGES["no_manage_users_rights"], show_alert=True)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в manage_users_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data.startswith("toggle_admin_"))
async def toggle_admin_handler(callback: CallbackQuery):
    """ИСПРАВЛЕНО: улучшенная диагностика и обработка ошибок"""
    try:
        user_id = int(callback.data.split("_")[2])
        
        # ОТЛАДКА: получаем информацию о пользователе перед изменением
        user_info = db.get_user_info(user_id)
        if user_info:
            current_user_id, username, current_admin_status = user_info
            logger.info(f"🔍 Попытка изменить права для: user_id={current_user_id}, username={username}, is_admin={current_admin_status}")
        else:
            logger.error(f"❌ Пользователь с ID {user_id} не найден в базе данных!")
            await callback.answer("❌ Пользователь не найден!", show_alert=True)
            return
        
        # Выполняем изменение статуса
        success = db.toggle_admin_status(user_id)
        
        if success:
            # Получаем обновленную информацию
            updated_info = db.get_user_info(user_id)
            if updated_info:
                _, username, new_admin_status = updated_info
                status_text = "администратором" if new_admin_status else "участником"
                
                await callback.answer(f"✅ Права изменены!\n\n👤 {username} теперь {status_text}")
                
                # ИСПРАВЛЕНО: перезагружаем список участников
                await manage_users_handler(callback)
            else:
                await callback.answer("❌ Ошибка получения обновленной информации", show_alert=True)
        else:
            await callback.answer("❌ Ошибка при изменении прав!", show_alert=True)
            
    except ValueError as e:
        logger.error(f"❌ Ошибка парсинга user_id из callback_data '{callback.data}': {e}")
        await callback.answer("❌ Ошибка обработки запроса", show_alert=True)
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в toggle_admin_handler: {e}")
        await callback.answer("❌ Произошла непредвиденная ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("remove_user_"))
async def remove_user_handler(callback: CallbackQuery):
    """ИСПРАВЛЕНО: улучшенная диагностика"""
    try:
        user_id = int(callback.data.split("_")[2])
        
        # ОТЛАДКА: получаем информацию о пользователе перед удалением
        user_info = db.get_user_info(user_id)
        if user_info:
            current_user_id, username, is_admin = user_info
            logger.info(f"🔍 Попытка удалить: user_id={current_user_id}, username={username}, is_admin={is_admin}")
        else:
            logger.error(f"❌ Пользователь с ID {user_id} не найден в базе данных!")
            await callback.answer("❌ Пользователь не найден!", show_alert=True)
            return
        
        success = db.remove_user_from_group(user_id)
        
        if success:
            await callback.answer(f"✅ Участник удален!\n\n👤 Пользователь исключен из группы")
            
            # ИСПРАВЛЕНО: перезагружаем список участников  
            await manage_users_handler(callback)
        else:
            await callback.answer("❌ Ошибка при удалении участника!", show_alert=True)
            
    except ValueError as e:
        logger.error(f"❌ Ошибка парсинга user_id из callback_data '{callback.data}': {e}")
        await callback.answer("❌ Ошибка обработки запроса", show_alert=True)
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в remove_user_handler: {e}")
        await callback.answer("❌ Произошла непредвиденная ошибка", show_alert=True)

# ВЫХОД ИЗ ГРУППЫ - ВОССТАНОВЛЕНО
@dp.callback_query(F.data == "leave_group")
async def leave_group_handler(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            MESSAGES["confirm_leave_group"],
            reply_markup=get_confirmation_keyboard()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в leave_group_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "confirm_leave")
async def confirm_leave_handler(callback: CallbackQuery):
    try:
        if db.remove_user_from_group(callback.from_user.id):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎓 Присоединиться к группе", callback_data="join_group")
            ]])
            await callback.message.edit_text("👋 <b>До свидания!</b>\n\n🚪 Вы успешно покинули группу\n📝 Личные заметки остались доступны\n🔄 Для продолжения работы присоединитесь к другой группе", reply_markup=keyboard)
            await callback.message.answer("🔄 Клавиатура обновлена", reply_markup=ReplyKeyboardRemove())
        else:
            await callback.answer(MESSAGES["error_occurred"], show_alert=True)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в confirm_leave_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "cancel_leave")
async def cancel_leave_handler(callback: CallbackQuery):
    try:
        user_group = db.get_user_group(callback.from_user.id)
        if user_group:
            group_id, is_admin = user_group
            group_name = db.get_group_name(group_id)
            
            cancelled_text = f"🔙 <b>Действие отменено</b>\n\n↩️ Возвращаемся в главное меню\n📊 Группа: <b>«{group_name}»</b>\n📝 Личные заметки: <b>Доступны</b>\n\n📌 Используйте кнопки ниже для навигации"
            
            await callback.message.edit_text(cancelled_text)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в cancel_leave_handler: {e}")
        await callback.answer(MESSAGES["error_occurred"], show_alert=True)

@dp.callback_query(F.data == "ignore")
async def ignore_handler(callback: CallbackQuery):
    await callback.answer()

# ОБРАБОТЧИКИ СОСТОЯНИЙ FSM - ВОССТАНОВЛЕНЫ
@dp.message(GroupStates.waiting_group_name)
async def process_group_name(message: Message, state: FSMContext):
    try:
        group_name = message.text.strip()
        if not group_name:
            await message.answer("❌ Название группы не может быть пустым. Попробуйте еще раз:")
            return
            
        await state.update_data(group_name=group_name)
        
        if db.group_exists(group_name):
            await message.answer("🔐 <b>Проверка доступа</b>\n\n🗝 Введите <b>пароль группы</b>:\n\n⚠️ <i>Убедитесь, что пароль введен правильно</i>")
            await state.set_state(GroupStates.waiting_group_password)
        else:
            await message.answer(f"🔒 <b>Создание новой группы</b>\n\n🚀 Группа \"<b>{group_name}</b>\" не существует!\n\n🔑 Для создания новой группы введите <b>мастер-пароль</b>:\n\n⚠️ <i>Обратитесь к администратору бота за мастер-паролем</i>")
            await state.set_state(GroupStates.waiting_master_password)
            
    except Exception as e:
        logger.error(f"Ошибка в process_group_name: {e}")
        await message.answer(MESSAGES["error_occurred"])
        await state.clear()

@dp.message(GroupStates.waiting_group_password)
async def process_group_password(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        group_name = data['group_name']
        password = message.text.strip()
        
        group_id = db.check_group_password(group_name, password)
        
        if group_id:
            if db.join_user_to_group(message.from_user.id, message.from_user.username, group_id):
                user_group = db.get_user_group(message.from_user.id)
                is_admin = user_group[1] if user_group else False
                
                await message.answer(
                    f"✅ <b>Успешно!</b>\n\n🎊 Добро пожаловать в группу <b>\"{group_name}\"</b>!\n📝 Также доступны личные заметки\n🏆 Теперь вы можете управлять домашними заданиями",
                    reply_markup=get_main_reply_keyboard(bool(is_admin))
                )
                await state.clear()
            else:
                await message.answer(MESSAGES["error_occurred"])
                await state.clear()
        else:
            await message.answer("❌ <b>Ошибка входа</b>\n\n🔍 Неверный пароль группы!\n\n💡 <i>Проверьте правильность пароля и попробуйте снова</i>")
            await message.answer("🔐 <b>Проверка доступа</b>\n\n🗝 Введите <b>пароль группы</b>:\n\n⚠️ <i>Убедитесь, что пароль введен правильно</i>")
        
    except Exception as e:
        logger.error(f"Ошибка в process_group_password: {e}")
        await message.answer(MESSAGES["error_occurred"])
        await state.clear()

@dp.message(GroupStates.waiting_master_password)
async def process_master_password(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        group_name = data['group_name']
        master_password = message.text.strip()
        
        if master_password == MASTER_PASSWORD:
            await message.answer(
                f"🔑 <b>Создание группы \"{group_name}\"</b>\n\n"
                f"✨ Придумайте <b>пароль для новой группы</b>:\n\n"
                f"💡 <i>Этот пароль будут использовать другие участники для входа в группу</i>"
            )
            await state.set_state(GroupStates.waiting_new_group_password)
        else:
            await message.answer("❌ <b>Неверный мастер-пароль!</b>\n\n🚫 У вас нет прав для создания новых групп\n📞 Обратитесь к администратору бота\n\n🔄 Попробуйте присоединиться к существующей группе")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎓 Присоединиться к группе", callback_data="join_group")
            ]])
            await message.answer("🎓 <b>Добро пожаловать в HomeworkBot!</b>\n\n📚 Ваш персональный помощник для управления домашними заданиями\n📝 Поддерживает как групповые, так и личные заметки\n\n✨ <i>Для начала работы присоединитесь к группе</i>", reply_markup=keyboard)
            await message.answer("🔄 Клавиатура обновлена", reply_markup=ReplyKeyboardRemove())
            await state.clear()
            
    except Exception as e:
        logger.error(f"Ошибка в process_master_password: {e}")
        await message.answer(MESSAGES["error_occurred"])
        await state.clear()

@dp.message(GroupStates.waiting_new_group_password)
async def process_new_group_password(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        group_name = data['group_name']
        password = message.text.strip()
        
        if not password:
            await message.answer("❌ Пароль не может быть пустым. Попробуйте еще раз:")
            return
        
        group_id = db.create_group(group_name, password)
        
        if group_id:
            if db.join_user_to_group(message.from_user.id, message.from_user.username, group_id, is_admin=True):
                await message.answer(
                    f"🎉 <b>Группа создана!</b>\n\n👑 Вы стали администратором группы <b>\"{group_name}\"</b>!\n📝 Личные заметки также доступны\n✨ Теперь вы можете добавлять участников и управлять заданиями",
                    reply_markup=get_main_reply_keyboard(True)
                )
            else:
                await message.answer(MESSAGES["error_occurred"])
        else:
            await message.answer(MESSAGES["error_occurred"])
        
        await state.clear()
            
    except Exception as e:
        logger.error(f"Ошибка в process_new_group_password: {e}")
        await message.answer(MESSAGES["error_occurred"])
        await state.clear()

@dp.message(GroupStates.waiting_homework_subject)
async def process_homework_subject(message: Message, state: FSMContext):
    try:
        subject = message.text.strip()
        if not subject:
            await message.answer("❌ Название предмета не может быть пустым. Попробуйте еще раз:")
            return
            
        await state.update_data(homework_subject=subject)
        await message.answer("📖 <b>Описание задания</b>\n\n✍️ Введите <b>текст домашнего задания</b>:\n\n💡 <i>Опишите задание максимально подробно</i>")
        await state.set_state(GroupStates.waiting_homework_text)
    except Exception as e:
        logger.error(f"Ошибка в process_homework_subject: {e}")
        await message.answer(MESSAGES["error_occurred"])
        await state.clear()

@dp.message(GroupStates.waiting_homework_text)
async def process_homework_text(message: Message, state: FSMContext):
    try:
        homework_text = message.text.strip()
        if not homework_text:
            await message.answer("❌ Текст задания не может быть пустым. Попробуйте еще раз:")
            return
            
        await state.update_data(homework_text=homework_text, homework_files=[])
        await message.answer(
            "📎 <b>Прикрепление файлов</b>\n\n"
            "✨ Хотите прикрепить файлы или фото к заданию?\n\n"
            "📷 Можете прикрепить фотографии\n"
            "📄 Можете прикрепить документы\n"
            "✅ Или завершить без файлов",
            reply_markup=get_homework_files_keyboard()
        )
        await state.set_state(GroupStates.waiting_homework_files)
    except Exception as e:
        logger.error(f"Ошибка в process_homework_text: {e}")
        await message.answer(MESSAGES["error_occurred"])
        await state.clear()

@dp.message(GroupStates.waiting_personal_subject)
async def process_personal_subject(message: Message, state: FSMContext):
    try:
        subject = message.text.strip()
        if not subject:
            await message.answer("❌ Название предмета не может быть пустым. Попробуйте еще раз:")
            return
            
        await state.update_data(homework_subject=subject)
        await message.answer("📖 <b>Текст заметки</b>\n\n✍️ Введите <b>текст личной заметки</b>:\n\n💡 <i>Опишите задание максимально подробно</i>")
        await state.set_state(GroupStates.waiting_personal_text)
    except Exception as e:
        logger.error(f"Ошибка в process_personal_subject: {e}")
        await message.answer(MESSAGES["error_occurred"])
        await state.clear()

@dp.message(GroupStates.waiting_personal_text)
async def process_personal_text(message: Message, state: FSMContext):
    try:
        homework_text = message.text.strip()
        if not homework_text:
            await message.answer("❌ Текст заметки не может быть пустым. Попробуйте еще раз:")
            return
            
        await state.update_data(homework_text=homework_text, homework_files=[])
        await message.answer(
            "📎 <b>Прикрепление файлов к заметке</b>\n\n"
            "✨ Хотите прикрепить файлы или фото к заметке?\n\n"
            "📷 Можете прикрепить фотографии\n"
            "📄 Можете прикрепить документы\n"
            "✅ Или завершить без файлов",
            reply_markup=get_homework_files_keyboard()
        )
        await state.set_state(GroupStates.waiting_personal_files)
    except Exception as e:
        logger.error(f"Ошибка в process_personal_text: {e}")
        await message.answer(MESSAGES["error_occurred"])
        await state.clear()

# ОБРАБОТЧИК ВСЕХ ОСТАЛЬНЫХ СООБЩЕНИЙ
@dp.message()
async def handle_unexpected_message(message: Message, state: FSMContext):
    try:
        current_state = await state.get_state()
        
        if current_state:
            await message.answer("❌ Пожалуйста, следуйте инструкциям или используйте кнопки навигации")
        else:
            user_group = db.get_user_group(message.from_user.id)
            if user_group:
                group_id, is_admin = user_group
                await message.answer(
                    "🤖 Используйте кнопки для навигации:",
                    reply_markup=get_main_reply_keyboard(bool(is_admin))
                )
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🎓 Присоединиться к группе", callback_data="join_group")
                ]])
                await message.answer(
                    "🤖 Для начала работы присоединитесь к группе:",
                    reply_markup=keyboard
                )
    except Exception as e:
        logger.error(f"Ошибка в handle_unexpected_message: {e}")
        await message.answer("⚠️ Произошла ошибка. Нажмите /start для перезапуска")

# ГЛАВНАЯ ФУНКЦИЯ
async def main():
    logger.info("🚀 Запуск ПОЛНОСТЬЮ исправленного HomeworkBot...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")

if __name__ == "__main__":
    asyncio.run(main())