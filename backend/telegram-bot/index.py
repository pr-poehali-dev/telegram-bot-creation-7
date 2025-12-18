'''
Бизнес: Telegram бот для пошагового создания заявок с маркетплейсами и умными уведомлениями
Аргументы: event - dict с httpMethod, body (telegram webhook)
Возвращает: HTTP response для Telegram API
'''

import json
import os
from typing import Dict, Any, Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from datetime import datetime, timedelta
import time
from collections import defaultdict
import ipaddress

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
ADMIN_CHAT_ID = os.environ.get('TELEGRAM_ADMIN_CHAT_ID', '')
PDF_FUNCTION_URL = 'https://functions.poehali.dev/bcfbb8a2-a68a-42ce-bfb2-f6bd9e33bbb5'

MARKETPLACES = [
    'Wildberries',
    'OZON',
    'Яндекс.Маркет',
    'AliExpress',
    'Другой'
]

user_states: Dict[int, Dict[str, Any]] = {}
admin_sessions: Dict[int, int] = {}
request_counts: Dict[int, list] = defaultdict(list)
SESSION_TIMEOUT = 6 * 60 * 60
ADMIN_SESSION_TIMEOUT = 24 * 60 * 60
MAX_REQUESTS_PER_MINUTE = 20
MAX_TEXT_LENGTH = 500
MAX_ORDERS_PER_DAY = 10
TELEGRAM_IPS = ['149.154.160.0/20', '91.108.4.0/22']

def normalize_warehouse(warehouse: str) -> str:
    """Нормализует название склада для fuzzy matching"""
    if not warehouse:
        return ''
    
    # Приводим к нижнему регистру
    normalized = warehouse.lower().strip()
    
    # Убираем лишние пробелы
    normalized = ' '.join(normalized.split())
    
    # Общие замены для частых опечаток
    replacements = {
        'коледино': 'каледино',
        'электросталь': 'електросталь',
        'подольск': 'падольск',
        'щелково': 'щолково',
        'чехов': 'чихов',
        'е': 'е',  # ё -> е
        'ё': 'е'
    }
    
    for wrong, correct in replacements.items():
        normalized = normalized.replace(wrong, correct)
    
    # Убираем все кроме букв, цифр и пробелов
    normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())
    
    return normalized

def is_telegram_request(ip: str) -> bool:
    if not ip:
        return True
    try:
        ip_addr = ipaddress.ip_address(ip)
        for cidr in TELEGRAM_IPS:
            if ip_addr in ipaddress.ip_network(cidr):
                return True
        return False
    except:
        return True


def is_rate_limited(chat_id: int) -> bool:
    now = time.time()
    requests_list = request_counts[chat_id]
    
    requests_list = [req for req in requests_list if now - req < 60]
    request_counts[chat_id] = requests_list
    
    if len(requests_list) >= MAX_REQUESTS_PER_MINUTE:
        return True
    
    requests_list.append(now)
    return False


def validate_text_length(text: str, max_length: int = MAX_TEXT_LENGTH) -> bool:
    return len(text) <= max_length


def log_security_event(chat_id: int, event_type: str, details: str, severity: str = 'medium'):
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.security_logs 
                (chat_id, event_type, details, severity)
                VALUES (%s, %s, %s, %s)
                """,
                (chat_id, event_type, details, severity)
            )
            conn.commit()
        conn.close()
    except:
        pass


def auto_block_user(chat_id: int, reason: str):
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.auto_blocked_users (chat_id, reason)
                VALUES (%s, %s)
                ON CONFLICT (chat_id) DO UPDATE SET reason = %s, blocked_at = CURRENT_TIMESTAMP
                """,
                (chat_id, reason, reason)
            )
            
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.blocked_users (chat_id)
                VALUES (%s)
                ON CONFLICT (chat_id) DO NOTHING
                """,
                (chat_id,)
            )
            
            conn.commit()
        conn.close()
        
        log_security_event(chat_id, 'auto_block', reason, 'high')
        notify_admin_about_block(chat_id, reason)
    except:
        pass


def notify_admin_about_block(chat_id: int, reason: str):
    try:
        admin_id = ADMIN_CHAT_ID
        if admin_id:
            message = f"""
🚨 <b>Автоматическая блокировка пользователя</b>

👤 Chat ID: <code>{chat_id}</code>
📋 Причина: {reason}
⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}

Проверьте логи в админ-панели.
"""
            send_message(int(admin_id), message)
    except:
        pass


def is_user_blocked(chat_id: int) -> bool:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chat_id FROM t_p52349012_telegram_bot_creatio.blocked_users WHERE chat_id = %s",
                (chat_id,)
            )
            result = cur.fetchone() is not None
        return result
    except:
        return False
    finally:
        conn.close()


def get_user_daily_limit(chat_id: int) -> int:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT daily_order_limit FROM t_p52349012_telegram_bot_creatio.user_limits WHERE chat_id = %s",
                (chat_id,)
            )
            result = cur.fetchone()
            return result[0] if result else MAX_ORDERS_PER_DAY
    except:
        return MAX_ORDERS_PER_DAY
    finally:
        conn.close()


def get_user_orders_today(chat_id: int) -> int:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT id FROM t_p52349012_telegram_bot_creatio.sender_orders
                    WHERE chat_id = %s AND created_at::date = CURRENT_DATE
                    UNION ALL
                    SELECT id FROM t_p52349012_telegram_bot_creatio.carrier_orders
                    WHERE chat_id = %s AND created_at::date = CURRENT_DATE
                ) AS combined
            """, (chat_id, chat_id))
            return cur.fetchone()[0]
    except:
        return 0
    finally:
        conn.close()


def check_suspicious_activity(chat_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.security_logs
                WHERE chat_id = %s AND created_at > NOW() - INTERVAL '1 hour'
            """, (chat_id,))
            
            events_last_hour = cur.fetchone()[0]
            
            if events_last_hour > 50:
                auto_block_user(chat_id, f'Подозрительная активность: {events_last_hour} событий за час')
                return True
            
            cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT id FROM t_p52349012_telegram_bot_creatio.sender_orders
                    WHERE chat_id = %s AND created_at::date = CURRENT_DATE
                    UNION ALL
                    SELECT id FROM t_p52349012_telegram_bot_creatio.carrier_orders
                    WHERE chat_id = %s AND created_at::date = CURRENT_DATE
                ) AS combined
            """, (chat_id, chat_id))
            
            orders_today = cur.fetchone()[0]
            user_limit = get_user_daily_limit(chat_id)
            
            if orders_today > user_limit * 2:
                auto_block_user(chat_id, f'Превышение лимита в 2 раза: {orders_today} заявок при лимите {user_limit}')
                return True
            
            return False
    except:
        return False
    finally:
        conn.close()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method: str = event.get('httpMethod', 'POST')
    
    print(f"Handler called: method={method}, event={json.dumps(event)[:200]}")
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }
    
    if method == 'GET':
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/plain'},
            'body': 'Telegram Bot is running',
            'isBase64Encoded': False
        }
    
    if method != 'POST':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }
    
    try:
        source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', '')
        
        if not is_telegram_request(source_ip):
            return {
                'statusCode': 403,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Forbidden'}),
                'isBase64Encoded': False
            }
        
        body_data = json.loads(event.get('body', '{}'))
        
        if 'callback_query' in body_data:
            callback = body_data['callback_query']
            chat_id = callback['message']['chat']['id']
            callback_data = callback['data']
            message_id = callback['message']['message_id']
            
            if is_user_blocked(chat_id):
                send_message(chat_id, "🚫 Ваш аккаунт заблокирован за подозрительную активность. Обратитесь к администратору.")
                log_security_event(chat_id, 'blocked_attempt', 'Попытка использовать бота после блокировки', 'high')
                return {
                    'statusCode': 403,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'User blocked'}),
                    'isBase64Encoded': False
                }
            
            if is_rate_limited(chat_id):
                log_security_event(chat_id, 'rate_limit', 'Превышен лимит запросов', 'medium')
                send_message(chat_id, "⏳ Слишком много запросов. Подождите минуту.")
                
                check_suspicious_activity(chat_id)
                
                return {
                    'statusCode': 429,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'Rate limit exceeded'}),
                    'isBase64Encoded': False
                }
            
            requests.post(
                f"{BASE_URL}/answerCallbackQuery",
                json={'callback_query_id': callback['id']}
            )
            
            process_callback(chat_id, callback_data, message_id)
            
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'ok': True}),
                'isBase64Encoded': False
            }
        
        if 'message' not in body_data:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'ok': True}),
                'isBase64Encoded': False
            }
        
        message = body_data['message']
        chat_id = message['chat']['id']
        text = message.get('text', '')
        
        if is_user_blocked(chat_id):
            send_message(chat_id, "🚫 Ваш аккаунт заблокирован за подозрительную активность. Обратитесь к администратору.")
            log_security_event(chat_id, 'blocked_attempt', 'Попытка использовать бота после блокировки', 'high')
            return {
                'statusCode': 403,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'User blocked'}),
                'isBase64Encoded': False
            }
        
        if is_rate_limited(chat_id):
            log_security_event(chat_id, 'rate_limit', 'Превышен лимит запросов', 'medium')
            send_message(chat_id, "⏳ Слишком много запросов. Подождите минуту.")
            
            check_suspicious_activity(chat_id)
            
            return {
                'statusCode': 429,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Rate limit exceeded'}),
                'isBase64Encoded': False
            }
        
        if not validate_text_length(text):
            log_security_event(chat_id, 'text_too_long', f'Текст {len(text)} символов', 'low')
            send_message(chat_id, f"❌ Текст слишком длинный (максимум {MAX_TEXT_LENGTH} символов)")
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Text too long'}),
                'isBase64Encoded': False
            }
        
        process_message(chat_id, text)
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'ok': True}),
            'isBase64Encoded': False
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)}),
            'isBase64Encoded': False
        }


def send_message(chat_id: int, text: str, reply_markup: Optional[Dict] = None):
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    requests.post(f"{BASE_URL}/sendMessage", json=payload)


def send_photo(chat_id: int, photo_url: str, caption: str = ''):
    payload = {
        'chat_id': chat_id,
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    requests.post(f"{BASE_URL}/sendPhoto", json=payload)


def send_document(chat_id: int, file_bytes: bytes, filename: str, caption: str = ''):
    files = {'document': (filename, file_bytes, 'application/pdf')}
    data = {
        'chat_id': chat_id,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    requests.post(f"{BASE_URL}/sendDocument", files=files, data=data)


def edit_message(chat_id: int, message_id: int, text: str, reply_markup: Optional[Dict] = None):
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    requests.post(f"{BASE_URL}/editMessageText", json=payload)


def process_callback(chat_id: int, callback_data: str, message_id: int):
    if chat_id not in user_states:
        send_message(chat_id, "Сессия истекла. Введите /start для начала")
        return
    
    state = user_states[chat_id]
    
    if time.time() - state.get('last_activity', 0) > SESSION_TIMEOUT:
        del user_states[chat_id]
        send_message(chat_id, "⏰ Сессия истекла (6 часов). Введите /start для начала")
        return
    
    state['last_activity'] = time.time()
    data = state.get('data', {})
    
    if callback_data.startswith('edit_'):
        field = callback_data.replace('edit_', '')
        state['editing_field'] = field
        
        field_names = {
            'marketplace': 'маркетплейс',
            'warehouse': 'склад назначения',
            'loading_address': 'адрес погрузки',
            'loading_date': 'дату погрузки (ДД.ММ.ГГГГ)',
            'loading_time': 'время погрузки',
            'pallet_quantity': 'количество паллет',
            'box_quantity': 'количество коробок',
            'sender_name': 'ФИО отправителя',
            'phone': 'номер телефона',
            'car_brand': 'марку автомобиля',
            'car_model': 'модель автомобиля',
            'license_plate': 'гос. номер',
            'pallet_capacity': 'вместимость паллет',
            'box_capacity': 'вместимость коробок',
            'driver_name': 'ФИО водителя',
            'arrival_date': 'дату прибытия на склад (ДД.ММ.ГГГГ)',
            'rate': 'ставку в рублях',
            'hydroboard': 'гидроборт'
        }
        
        if field == 'hydroboard':
            send_message(
                chat_id,
                "🚚 <b>Гидроборт</b>",
                {
                    'keyboard': [
                        [{'text': 'Есть'}],
                        [{'text': 'Нету'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
            )
        elif field in ['loading_date', 'arrival_date']:
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            send_message(
                chat_id,
                f"✏️ Введите новое значение для <b>{field_names.get(field, field)}</b>:\n\nВыберите из вариантов или введите дату вручную\nФормат: ДД.ММ.ГГГГ",
                {
                    'keyboard': [
                        [{'text': f'🔴 Сегодня ({today.strftime("%d.%m.%Y")})'}],
                        [{'text': f'🟢 Завтра ({tomorrow.strftime("%d.%m.%Y")})'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
            )
        else:
            send_message(
                chat_id,
                f"✏️ Введите новое значение для <b>{field_names.get(field, field)}</b>:"
            )
    
    elif callback_data == 'confirm_create':
        if data.get('type') == 'sender':
            save_sender_order(chat_id, data)
            if chat_id in user_states:
                del user_states[chat_id]
        else:
            save_carrier_order(chat_id, data)
            if chat_id in user_states:
                del user_states[chat_id]
    
    elif callback_data.startswith('admin_'):
        if str(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "❌ У вас нет прав администратора")
            return
        
        if callback_data == 'admin_exit':
            if chat_id in admin_sessions:
                del admin_sessions[chat_id]
            send_message(
                chat_id,
                "👋 Вы вышли из админ-панели. Введите /start для возврата к основному меню.",
                {'remove_keyboard': True}
            )
            return
        
        admin_sessions[chat_id] = int(time.time())
        
        if callback_data == 'admin_stats':
            show_admin_stats(chat_id)
        elif callback_data == 'admin_weekly':
            show_weekly_stats(chat_id)
        elif callback_data == 'admin_delete':
            state['admin_action'] = 'delete'
            send_message(chat_id, "📝 Введите ID заявки для удаления (например: 123)")
        elif callback_data == 'admin_cleanup':
            cleanup_old_orders(chat_id)
        elif callback_data == 'admin_security_logs':
            show_security_logs(chat_id)
        elif callback_data == 'admin_blocked_users':
            show_blocked_users(chat_id)
        elif callback_data == 'admin_set_limit':
            state['admin_action'] = 'set_limit'
            send_message(chat_id, "📝 Введите Chat ID пользователя и новый лимит через пробел\n\nНапример: 123456789 50")
    
    elif callback_data.startswith('delete_order_'):
        order_id = int(callback_data.replace('delete_order_', ''))
        delete_user_order(chat_id, order_id)
    
    elif callback_data == 'my_orders':
        show_my_orders(chat_id)
    
    elif callback_data == 'cancel_create':
        user_states[chat_id] = {'step': 'choose_service', 'data': {}}
        send_message(
            chat_id,
            "❌ Создание заявки отменено\n\n<b>Выберите услугу:</b>",
            {
                'keyboard': [
                    [{'text': '📦 Отправитель'}],
                    [{'text': '🚚 Перевозчик'}]
                ],
                'resize_keyboard': True
            }
        )


def process_message(chat_id: int, text: str):
    if text.startswith('/unblock '):
        if str(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "❌ У вас нет прав администратора")
            return
        
        try:
            target_chat_id = int(text.split()[1])
            unblock_user(chat_id, target_chat_id)
        except (ValueError, IndexError):
            send_message(chat_id, "❌ Неверный формат. Используйте: /unblock CHAT_ID")
        return
    
    if text == '/admin':
        if str(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "❌ У вас нет прав администратора")
            return
        
        admin_sessions[chat_id] = int(time.time())
        
        send_message(
            chat_id,
            "🔧 <b>Админ-панель</b>\n\n" +
            "Выберите действие:",
            {
                'inline_keyboard': [
                    [{'text': '📊 Статистика', 'callback_data': 'admin_stats'}],
                    [{'text': '📈 Еженедельный отчёт', 'callback_data': 'admin_weekly'}],
                    [{'text': '🔒 Логи безопасности', 'callback_data': 'admin_security_logs'}],
                    [{'text': '🚫 Заблокированные', 'callback_data': 'admin_blocked_users'}],
                    [{'text': '⚙️ Установить лимит', 'callback_data': 'admin_set_limit'}],
                    [{'text': '🗑️ Удалить заявку', 'callback_data': 'admin_delete'}],
                    [{'text': '🧹 Очистить старые заявки', 'callback_data': 'admin_cleanup'}],
                    [{'text': '🏠 Выйти из админ-панели', 'callback_data': 'admin_exit'}]
                ]
            }
        )
        return
    
    if text == '/start':
        user_states[chat_id] = {'step': 'choose_service', 'data': {}, 'last_activity': time.time()}
        send_message(
            chat_id,
            "👋 <b>Добро пожаловать!</b>\n\n"
            "⚠️ <b>Важно:</b>\n"
            "• Сохраняйте скрины переписок\n"
            "• Сверяйте данные авто с заявкой\n"
            "• Будьте внимательны к деталям\n\n"
            "<b>Выберите услугу:</b>",
            {
                'keyboard': [
                    [{'text': '📦 Отправитель'}],
                    [{'text': '🚚 Перевозчик'}],
                    [{'text': '📋 Мои заявки'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': False
            }
        )
        return
    
    if chat_id not in user_states:
        user_states[chat_id] = {'step': 'choose_service', 'data': {}, 'last_activity': time.time()}
        send_message(
            chat_id,
            "Введите /start чтобы начать",
            {'remove_keyboard': True}
        )
        return
    
    state = user_states[chat_id]
    
    if time.time() - state.get('last_activity', 0) > SESSION_TIMEOUT:
        del user_states[chat_id]
        send_message(chat_id, "⏰ Сессия истекла (6 часов). Введите /start для начала")
        return
    
    state['last_activity'] = time.time()
    step = state['step']
    data = state['data']
    
    if state.get('admin_action'):
        action = state['admin_action']
        
        if action == 'delete':
            try:
                order_id = int(text)
                delete_order_admin(chat_id, order_id)
            except ValueError:
                send_message(chat_id, "❌ Неверный формат ID")
        
        elif action == 'set_limit':
            try:
                parts = text.split()
                if len(parts) != 2:
                    send_message(chat_id, "❌ Неверный формат. Используйте: Chat_ID Лимит")
                    del state['admin_action']
                    return
                
                target_chat_id = int(parts[0])
                new_limit = int(parts[1])
                
                if new_limit < 1 or new_limit > 100:
                    send_message(chat_id, "❌ Лимит должен быть от 1 до 100")
                    del state['admin_action']
                    return
                
                set_user_limit(target_chat_id, new_limit)
                send_message(chat_id, f"✅ Лимит для пользователя {target_chat_id} установлен: {new_limit} заявок/день")
            except ValueError:
                send_message(chat_id, "❌ Неверный формат. Используйте: Chat_ID Лимит")
        
        if 'admin_action' in state:
            del state['admin_action']
        return
    
    if state.get('editing_field'):
        field = state['editing_field']
        
        if field in ['pallet_quantity', 'box_quantity', 'pallet_capacity', 'box_capacity', 'rate']:
            data[field] = int(text) if text.isdigit() else 0
        elif field in ['loading_date', 'arrival_date']:
            try:
                if 'сегодня' in text.lower() or '🔴' in text:
                    date_obj = datetime.now()
                elif 'завтра' in text.lower() or '🟢' in text:
                    date_obj = datetime.now() + timedelta(days=1)
                else:
                    text_cleaned = text.replace('🔴', '').replace('🟢', '').strip()
                    text_cleaned = text_cleaned.split('(')[-1].replace(')', '').strip() if '(' in text_cleaned else text_cleaned
                    date_obj = datetime.strptime(text_cleaned, '%d.%m.%Y')
                data[field] = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
                return
        elif field == 'hydroboard':
            data[field] = 'Есть' if 'есть' in text.lower() else 'Нету'
        else:
            data[field] = text
        
        del state['editing_field']
        show_preview(chat_id, data)
        return
    
    if step == 'setup_notifications':
        handle_notification_setup(chat_id, text, data)
        return
    
    if step == 'choose_service':
        if '📦' in text or 'отправитель' in text.lower():
            data['type'] = 'sender'
            state['step'] = 'choose_marketplace'
            
            keyboard = [[{'text': mp}] for mp in MARKETPLACES]
            send_message(
                chat_id,
                "🏪 <b>Выберите маркетплейс:</b>",
                {'keyboard': keyboard, 'resize_keyboard': True, 'one_time_keyboard': True}
            )
        elif '🚚' in text or 'перевозчик' in text.lower():
            data['type'] = 'carrier'
            state['step'] = 'choose_marketplace'
            
            keyboard = [[{'text': mp}] for mp in MARKETPLACES]
            send_message(
                chat_id,
                "🏪 <b>Выберите маркетплейс:</b>",
                {'keyboard': keyboard, 'resize_keyboard': True, 'one_time_keyboard': True}
            )
        else:
            send_message(chat_id, "Пожалуйста, выберите услугу из меню")
    
    elif step == 'choose_marketplace':
        data['marketplace'] = text
        
        if data['type'] == 'sender':
            state['step'] = 'sender_warehouse'
            send_message(chat_id, "📍 <b>Укажите склад назначения</b>\n\nНапример: Электросталь", {'remove_keyboard': True})
        else:
            state['step'] = 'carrier_warehouse'
            send_message(
                chat_id,
                "📍 <b>Укажите склад назначения</b>\n\nНапример: Электросталь",
                {
                    'keyboard': [[{'text': '📦 Любой склад'}]],
                    'resize_keyboard': True,
                    'one_time_keyboard': False
                }
            )
    
    elif step == 'sender_warehouse':
        data['warehouse'] = text
        state['step'] = 'sender_loading_address'
        send_message(chat_id, "🏠 <b>Укажите адрес погрузки</b>\n\nНапример: г. Москва, ул. Ленина, д. 10")
    
    elif step == 'sender_loading_address':
        data['loading_address'] = text
        state['step'] = 'sender_loading_date'
        send_message(chat_id, "📅 <b>Укажите дату погрузки</b>\n\nФормат: ДД.ММ.ГГГГ\nНапример: 25.12.2025")
    
    elif step == 'sender_loading_date':
        try:
            loading_date = datetime.strptime(text, '%d.%m.%Y')
            data['loading_date'] = loading_date.strftime('%Y-%m-%d')
            
            days_until = (loading_date - datetime.now()).days
            if days_until > 1:
                send_message(
                    chat_id,
                    f"⚠️ <b>Внимание!</b> Заявка будет автоматически удалена через 24 часа после указанной даты поставки.\n\n" +
                    f"Дата поставки: {loading_date.strftime('%d.%m.%Y')}\n" +
                    f"Заявка будет удалена: {(loading_date + timedelta(days=1)).strftime('%d.%m.%Y')}"
                )
            
            state['step'] = 'sender_loading_time'
            send_message(chat_id, "🕐 <b>Укажите время погрузки</b>\n\nФормат: ЧЧ:ММ\nНапример: 14:30")
        except ValueError:
            send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
    
    elif step == 'sender_loading_time':
        data['loading_time'] = text
        state['step'] = 'sender_pallet_quantity'
        send_message(chat_id, "📦 <b>Укажите количество паллет</b>\n\nНапример: 5\nИли 0, если нет паллет")
    
    elif step == 'sender_pallet_quantity':
        data['pallet_quantity'] = int(text) if text.isdigit() else 0
        state['step'] = 'sender_box_quantity'
        send_message(chat_id, "📦 <b>Укажите количество коробок</b>\n\nНапример: 10\nИли 0, если нет коробок")
    
    elif step == 'sender_box_quantity':
        data['box_quantity'] = int(text) if text.isdigit() else 0
        state['step'] = 'sender_name'
        send_message(chat_id, "👤 <b>Укажите ФИО отправителя</b>\n\nНапример: Иванов Иван Иванович")
    
    elif step == 'sender_name':
        data['sender_name'] = text
        state['step'] = 'sender_phone'
        send_message(chat_id, "📱 <b>Укажите номер телефона</b>\n\nФормат: +79991234567")
    
    elif step == 'sender_phone':
        phone = text.strip()
        if phone.startswith('8'):
            phone = '+7' + phone[1:]
        elif not phone.startswith('+'):
            phone = '+7' + phone
        data['phone'] = phone
        state['step'] = 'sender_rate'
        send_message(chat_id, "💵 <b>Укажите желаемую ставку в рублях</b>\n\nНапример: 5000", {'remove_keyboard': True})
    
    elif step == 'sender_rate':
        if text.isdigit():
            data['rate'] = int(text)
            state['step'] = 'sender_label_size'
            send_message(
                chat_id,
                "🏷️ <b>Выберите термоэтикетку с инфо для водителя</b>",
                {
                    'keyboard': [
                        [{'text': '120x75 мм'}],
                        [{'text': '58x40 мм'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
            )
        else:
            send_message(chat_id, "❌ Неверный формат. Укажите цифру. Например: 5000")
    
    elif step == 'sender_label_size':
        if '120' in text:
            data['label_size'] = '120x75'
        else:
            data['label_size'] = '58x40'
        
        send_message(chat_id, "📋 Термоэтикетка будет отправлена после создания заявки")
        state['step'] = 'show_preview'
        show_preview(chat_id, data)
    
    elif step == 'carrier_warehouse':
        if 'любой' in text.lower():
            data['warehouse'] = 'Любой склад'
        else:
            data['warehouse'] = text
        state['step'] = 'carrier_car_brand'
        send_message(chat_id, "🚗 <b>Укажите марку автомобиля</b>\n\nНапример: Mercedes", {'remove_keyboard': True})
    
    elif step == 'carrier_car_brand':
        data['car_brand'] = text
        state['step'] = 'carrier_car_model'
        send_message(chat_id, "🚗 <b>Укажите модель автомобиля</b>\n\nНапример: Sprinter")
    
    elif step == 'carrier_car_model':
        data['car_model'] = text
        state['step'] = 'carrier_license_plate'
        send_message(chat_id, "🔢 <b>Укажите гос. номер автомобиля</b>\n\nНапример: А000АА777")
    
    elif step == 'carrier_license_plate':
        data['license_plate'] = text
        state['step'] = 'carrier_pallet_capacity'
        send_message(chat_id, "📦 <b>Укажите вместимость паллет</b>\n\nНапример: 10\nИли 0, если не перевозите паллеты")
    
    elif step == 'carrier_pallet_capacity':
        data['pallet_capacity'] = int(text) if text.isdigit() else 0
        state['step'] = 'carrier_box_capacity'
        send_message(chat_id, "📦 <b>Укажите вместимость коробок</b>\n\nНапример: 50\nИли 0, если не перевозите коробки")
    
    elif step == 'carrier_box_capacity':
        data['box_capacity'] = int(text) if text.isdigit() else 0
        state['step'] = 'carrier_driver_name'
        send_message(chat_id, "👤 <b>Укажите ФИО водителя</b>\n\nНапример: Петров Петр Петрович")
    
    elif step == 'carrier_driver_name':
        data['driver_name'] = text
        state['step'] = 'carrier_phone'
        send_message(chat_id, "📱 <b>Укажите номер телефона</b>\n\nФормат: +79991234567")
    
    elif step == 'carrier_phone':
        phone = text.strip()
        if phone.startswith('8'):
            phone = '+7' + phone[1:]
        elif not phone.startswith('+'):
            phone = '+7' + phone
        data['phone'] = phone
        state['step'] = 'carrier_hydroboard'
        send_message(
            chat_id,
            "🚚 <b>Гидроборт</b>",
            {
                'keyboard': [
                    [{'text': 'Есть'}],
                    [{'text': 'Нету'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'carrier_hydroboard':
        data['hydroboard'] = 'Есть' if 'есть' in text.lower() else 'Нету'
        state['step'] = 'carrier_loading_date'
        
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        
        send_message(
            chat_id,
            "📅 <b>Укажите желаемую дату погрузки</b>\n\nВыберите из вариантов или введите дату вручную\nФормат: ДД.ММ.ГГГГ",
            {
                'keyboard': [
                    [{'text': f'🔴 Сегодня ({today.strftime("%d.%m.%Y")})'}],
                    [{'text': f'🟢 Завтра ({tomorrow.strftime("%d.%m.%Y")})'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'carrier_loading_date':
        try:
            if 'сегодня' in text.lower() or '🔴' in text:
                loading_date = datetime.now()
            elif 'завтра' in text.lower() or '🟢' in text:
                loading_date = datetime.now() + timedelta(days=1)
            else:
                text_cleaned = text.replace('🔴', '').replace('🟢', '').strip()
                text_cleaned = text_cleaned.split('(')[-1].replace(')', '').strip() if '(' in text_cleaned else text_cleaned
                loading_date = datetime.strptime(text_cleaned, '%d.%m.%Y')
            
            data['loading_date'] = loading_date.strftime('%Y-%m-%d')
            state['step'] = 'carrier_arrival_date'
            
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            
            send_message(
                chat_id,
                "📅 <b>Укажите дату прибытия на склад</b>\n\nВыберите из вариантов или введите дату вручную\nФормат: ДД.ММ.ГГГГ",
                {
                    'keyboard': [
                        [{'text': f'🔴 Сегодня ({today.strftime("%d.%m.%Y")})'}],
                        [{'text': f'🟢 Завтра ({tomorrow.strftime("%d.%m.%Y")})'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
            )
        except ValueError:
            send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
    
    elif step == 'carrier_arrival_date':
        try:
            if 'сегодня' in text.lower() or '🔴' in text:
                arrival_date = datetime.now()
            elif 'завтра' in text.lower() or '🟢' in text:
                arrival_date = datetime.now() + timedelta(days=1)
            else:
                text_cleaned = text.replace('🔴', '').replace('🟢', '').strip()
                text_cleaned = text_cleaned.split('(')[-1].replace(')', '').strip() if '(' in text_cleaned else text_cleaned
                arrival_date = datetime.strptime(text_cleaned, '%d.%m.%Y')
            
            data['arrival_date'] = arrival_date.strftime('%Y-%m-%d')
            
            user_states[chat_id]['step'] = 'show_preview'
            show_preview(chat_id, data)
        except ValueError:
            send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")


def generate_and_send_label(chat_id: int, data: Dict[str, Any]):
    send_message(chat_id, "⏳ Генерирую термоэтикетку на русском языке...")
    send_message(chat_id, "📋 Термоэтикетка будет отправлена после создания заявки")


def send_label_to_user(chat_id: int, order_id: int, order_type: str, label_size: str):
    try:
        import base64
        
        response = requests.post(
            PDF_FUNCTION_URL,
            json={
                'order_id': order_id,
                'order_type': order_type,
                'label_size': label_size
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            pdf_base64 = result.get('pdf')
            filename = result.get('filename', f'label_{order_id}.pdf')
            
            if pdf_base64:
                pdf_bytes = base64.b64decode(pdf_base64)
                send_document(chat_id, pdf_bytes, filename, f"📄 Термоэтикетка для заявки #{order_id}")
            else:
                send_message(chat_id, "❌ Ошибка: не удалось получить PDF")
        else:
            send_message(chat_id, f"❌ Ошибка генерации термоэтикетки (код {response.status_code})")
    
    except Exception as e:
        send_message(chat_id, f"❌ Ошибка отправки термоэтикетки: {str(e)}")


def show_preview(chat_id: int, data: Dict[str, Any]):
    if data['type'] == 'sender':
        preview_text = (
            "📋 <b>ПРЕВЬЮ ЗАЯВКИ ОТПРАВИТЕЛЯ</b>\n\n"
            f"🏪 Маркетплейс: {data.get('marketplace', '-')}\n"
            f"📍 Склад: {data.get('warehouse', '-')}\n"
            f"🏠 Адрес погрузки: {data.get('loading_address', '-')}\n"
            f"📅 Дата погрузки: {data.get('loading_date', '-')}\n"
            f"🕐 Время погрузки: {data.get('loading_time', '-')}\n"
            f"📦 Паллеты: {data.get('pallet_quantity', 0)}\n"
            f"📦 Коробки: {data.get('box_quantity', 0)}\n"
            f"👤 Отправитель: {data.get('sender_name', '-')}\n"
            f"📱 Телефон: {data.get('phone', '-')}\n"
            f"💵 Ставка: {data.get('rate', '-')} руб.\n"
            f"🏷️ Термоэтикетка: {data.get('label_size', '-')}"
        )
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '✏️ Маркетплейс', 'callback_data': 'edit_marketplace'},
                    {'text': '✏️ Склад', 'callback_data': 'edit_warehouse'}
                ],
                [
                    {'text': '✏️ Адрес', 'callback_data': 'edit_loading_address'},
                    {'text': '✏️ Дата', 'callback_data': 'edit_loading_date'}
                ],
                [
                    {'text': '✏️ Время', 'callback_data': 'edit_loading_time'},
                    {'text': '✏️ Паллеты', 'callback_data': 'edit_pallet_quantity'}
                ],
                [
                    {'text': '✏️ Коробки', 'callback_data': 'edit_box_quantity'},
                    {'text': '✏️ ФИО', 'callback_data': 'edit_sender_name'}
                ],
                [
                    {'text': '✏️ Телефон', 'callback_data': 'edit_phone'},
                    {'text': '✏️ Ставка', 'callback_data': 'edit_rate'}
                ],
                [
                    {'text': '✅ СОЗДАТЬ ЗАЯВКУ', 'callback_data': 'confirm_create'}
                ],
                [
                    {'text': '❌ Отменить', 'callback_data': 'cancel_create'}
                ]
            ]
        }
    else:
        preview_text = (
            "📋 <b>ПРЕВЬЮ ЗАЯВКИ ПЕРЕВОЗЧИКА</b>\n\n"
            f"🏪 Маркетплейс: {data.get('marketplace', '-')}\n"
            f"📍 Склад: {data.get('warehouse', '-')}\n"
            f"🚗 Марка: {data.get('car_brand', '-')}\n"
            f"🚗 Модель: {data.get('car_model', '-')}\n"
            f"🔢 Гос. номер: {data.get('license_plate', '-')}\n"
            f"📦 Вместимость паллет: {data.get('pallet_capacity', 0)}\n"
            f"📦 Вместимость коробок: {data.get('box_capacity', 0)}\n"
            f"🚚 Гидроборт: {data.get('hydroboard', '-')}\n"
            f"👤 Водитель: {data.get('driver_name', '-')}\n"
            f"📱 Телефон: {data.get('phone', '-')}\n"
            f"📅 Дата погрузки: {data.get('loading_date', '-')}\n"
            f"📅 Дата прибытия: {data.get('arrival_date', '-')}"
        )
        
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '✏️ Маркетплейс', 'callback_data': 'edit_marketplace'},
                    {'text': '✏️ Склад', 'callback_data': 'edit_warehouse'}
                ],
                [
                    {'text': '✏️ Марка', 'callback_data': 'edit_car_brand'},
                    {'text': '✏️ Модель', 'callback_data': 'edit_car_model'}
                ],
                [
                    {'text': '✏️ Номер', 'callback_data': 'edit_license_plate'},
                    {'text': '✏️ Паллеты', 'callback_data': 'edit_pallet_capacity'}
                ],
                [
                    {'text': '✏️ Коробки', 'callback_data': 'edit_box_capacity'},
                    {'text': '✏️ Гидроборт', 'callback_data': 'edit_hydroboard'}
                ],
                [
                    {'text': '✏️ Водитель', 'callback_data': 'edit_driver_name'},
                    {'text': '✏️ Телефон', 'callback_data': 'edit_phone'}
                ],
                [
                    {'text': '✏️ Дата погрузки', 'callback_data': 'edit_loading_date'},
                    {'text': '✏️ Дата прибытия', 'callback_data': 'edit_arrival_date'}
                ],
                [
                    {'text': '✅ СОЗДАТЬ ЗАЯВКУ', 'callback_data': 'confirm_create'}
                ],
                [
                    {'text': '❌ Отменить', 'callback_data': 'cancel_create'}
                ]
            ]
        }
    
    send_message(chat_id, preview_text, keyboard)


def save_sender_order(chat_id: int, data: Dict[str, Any]):
    user_limit = get_user_daily_limit(chat_id)
    orders_today = get_user_orders_today(chat_id)
    
    if orders_today >= user_limit:
        log_security_event(chat_id, 'order_limit_exceeded', f'Попытка создать {orders_today + 1} заявку при лимите {user_limit}', 'medium')
        send_message(
            chat_id,
            f"❌ <b>Превышен лимит заявок</b>\n\nВы можете создать максимум {user_limit} заявок в день.\nПопробуйте завтра.",
            {'remove_keyboard': True}
        )
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            warehouse_norm = normalize_warehouse(data.get('warehouse', ''))
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.sender_orders
                (loading_address, warehouse, loading_date, loading_time, pallet_quantity, box_quantity, sender_name, phone, label_size, marketplace, chat_id, rate, warehouse_normalized)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    data.get('loading_address'),
                    data.get('warehouse'),
                    data.get('loading_date'),
                    data.get('loading_time'),
                    data.get('pallet_quantity', 0),
                    data.get('box_quantity', 0),
                    data.get('sender_name'),
                    data.get('phone'),
                    data.get('label_size'),
                    data.get('marketplace'),
                    chat_id,
                    data.get('rate'),
                    warehouse_norm
                )
            )
            
            order_id = cur.fetchone()['id']
            conn.commit()
            
            send_message(
                chat_id,
                f"✅ <b>Заявка #{order_id} создана!</b>\n\nПеревозчики получили уведомление о вашем грузе.",
                {'remove_keyboard': True}
            )
            
            send_label_to_user(chat_id, order_id, 'sender', data.get('label_size', '120x75'))
            
            notify_about_new_order(order_id, 'sender', data)
            send_notifications_to_subscribers(order_id, 'sender', data)
            find_matching_orders_by_date(order_id, 'sender', data)
            ask_notification_settings(chat_id, 'sender', data)
    
    finally:
        conn.close()


def save_carrier_order(chat_id: int, data: Dict[str, Any]):
    user_limit = get_user_daily_limit(chat_id)
    orders_today = get_user_orders_today(chat_id)
    
    if orders_today >= user_limit:
        log_security_event(chat_id, 'order_limit_exceeded', f'Попытка создать {orders_today + 1} заявку при лимите {user_limit}', 'medium')
        send_message(
            chat_id,
            f"❌ <b>Превышен лимит заявок</b>\n\nВы можете создать максимум {user_limit} заявок в день.\nПопробуйте завтра.",
            {'remove_keyboard': True}
        )
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            warehouse_norm = normalize_warehouse(data.get('warehouse', ''))
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.carrier_orders
                (warehouse, car_brand, car_model, license_plate, pallet_capacity, box_capacity, driver_name, phone, marketplace, loading_date, arrival_date, hydroboard, chat_id, warehouse_normalized)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    data.get('warehouse'),
                    data.get('car_brand'),
                    data.get('car_model'),
                    data.get('license_plate'),
                    data.get('pallet_capacity', 0),
                    data.get('box_capacity', 0),
                    data.get('driver_name'),
                    data.get('phone'),
                    data.get('marketplace'),
                    data.get('loading_date'),
                    data.get('arrival_date'),
                    data.get('hydroboard'),
                    chat_id,
                    warehouse_norm
                )
            )
            
            order_id = cur.fetchone()['id']
            conn.commit()
            
            send_message(
                chat_id,
                f"✅ <b>Заявка #{order_id} создана!</b>\n\nОтправители получили уведомление о вашем предложении.",
                {'remove_keyboard': True}
            )
            
            notify_about_new_order(order_id, 'carrier', data)
            send_notifications_to_subscribers(order_id, 'carrier', data)
            find_matching_orders_by_date(order_id, 'carrier', data)
            ask_notification_settings(chat_id, 'carrier', data)
    
    finally:
        conn.close()


def get_blocked_users() -> list:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM t_p52349012_telegram_bot_creatio.blocked_users")
            return [str(row[0]) for row in cur.fetchall()]
    except:
        return []
    finally:
        conn.close()


def show_admin_stats(chat_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.sender_orders")
            sender_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.carrier_orders")
            carrier_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.blocked_users")
            blocked_count = cur.fetchone()[0]
            
            cur.execute("""
                SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.sender_orders 
                WHERE loading_date < CURRENT_DATE - INTERVAL '1 day'
            """)
            old_sender = cur.fetchone()[0]
            
            stats_text = (
                f"📊 <b>Статистика бота</b>\n\n"
                f"📦 Заявок отправителей: {sender_count}\n"
                f"🚚 Заявок перевозчиков: {carrier_count}\n"
                f"🚫 Заблокировано пользователей: {blocked_count}\n"
                f"⏰ Устаревших заявок: {old_sender}"
            )
            
            send_message(chat_id, stats_text)
    finally:
        conn.close()


def handle_admin_input(chat_id: int, text: str, action: str):
    state = user_states[chat_id]
    
    if action == 'delete':
        if not text.isdigit():
            send_message(chat_id, "❌ Неверный ID. Введите число.")
            return
        
        order_id = int(text)
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE id = %s",
                    (order_id,)
                )
                if cur.rowcount == 0:
                    cur.execute(
                        "DELETE FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE id = %s",
                        (order_id,)
                    )
                
                conn.commit()
                
                if cur.rowcount > 0:
                    send_message(chat_id, f"✅ Заявка #{order_id} удалена")
                else:
                    send_message(chat_id, f"❌ Заявка #{order_id} не найдена")
        finally:
            conn.close()
        
        del state['admin_action']
    
    elif action == 'block':
        if not text.isdigit():
            send_message(chat_id, "❌ Неверный Chat ID. Введите число.")
            return
        
        user_chat_id = int(text)
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO t_p52349012_telegram_bot_creatio.blocked_users (chat_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (user_chat_id,)
                )
                conn.commit()
                send_message(chat_id, f"✅ Пользователь {user_chat_id} заблокирован")
        finally:
            conn.close()
        
        del state['admin_action']
    
    elif action == 'unblock':
        if not text.isdigit():
            send_message(chat_id, "❌ Неверный Chat ID. Введите число.")
            return
        
        user_chat_id = int(text)
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM t_p52349012_telegram_bot_creatio.blocked_users WHERE chat_id = %s",
                    (user_chat_id,)
                )
                conn.commit()
                send_message(chat_id, f"✅ Пользователь {user_chat_id} разблокирован")
        finally:
            conn.close()
        
        del state['admin_action']


def cleanup_old_orders(chat_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM t_p52349012_telegram_bot_creatio.sender_orders 
                WHERE loading_date < CURRENT_DATE - INTERVAL '1 day'
            """)
            deleted_count = cur.rowcount
            conn.commit()
            
            send_message(chat_id, f"🧹 Удалено старых заявок: {deleted_count}")
    finally:
        conn.close()


def show_weekly_stats(chat_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            week_ago = datetime.now() - timedelta(days=7)
            week_ago_str = week_ago.strftime('%Y-%m-%d')
            
            cur.execute("""
                SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.sender_orders 
                WHERE created_at >= %s
            """, (week_ago_str,))
            new_sender = cur.fetchone()[0]
            
            cur.execute("""
                SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.carrier_orders 
                WHERE created_at >= %s
            """, (week_ago_str,))
            new_carrier = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.sender_orders")
            total_sender = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.carrier_orders")
            total_carrier = cur.fetchone()[0]
            
            cur.execute("""
                SELECT marketplace, COUNT(*) as cnt 
                FROM t_p52349012_telegram_bot_creatio.sender_orders 
                WHERE created_at >= %s AND marketplace IS NOT NULL
                GROUP BY marketplace 
                ORDER BY cnt DESC 
                LIMIT 3
            """, (week_ago_str,))
            top_marketplaces = cur.fetchall()
            
            cur.execute("""
                SELECT warehouse, COUNT(*) as cnt 
                FROM t_p52349012_telegram_bot_creatio.sender_orders 
                WHERE created_at >= %s AND warehouse IS NOT NULL
                GROUP BY warehouse 
                ORDER BY cnt DESC 
                LIMIT 3
            """, (week_ago_str,))
            top_warehouses = cur.fetchall()
            
            stats_text = (
                f"📈 <b>ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ</b>\n"
                f"📅 {week_ago.strftime('%d.%m.%Y')} - {datetime.now().strftime('%d.%m.%Y')}\n\n"
                f"📊 <b>Новые заявки за неделю:</b>\n"
                f"📦 Отправителей: {new_sender}\n"
                f"🚚 Перевозчиков: {new_carrier}\n"
                f"📊 Всего: {new_sender + new_carrier}\n\n"
                f"📊 <b>Общая статистика:</b>\n"
                f"📦 Всего отправителей: {total_sender}\n"
                f"🚚 Всего перевозчиков: {total_carrier}\n"
            )
            
            if top_marketplaces:
                stats_text += "\n🏪 <b>Топ маркетплейсов недели:</b>\n"
                for mp, cnt in top_marketplaces:
                    stats_text += f"• {mp}: {cnt} заявок\n"
            
            if top_warehouses:
                stats_text += "\n📍 <b>Топ складов недели:</b>\n"
                for wh, cnt in top_warehouses:
                    stats_text += f"• {wh}: {cnt} заявок\n"
            
            send_message(chat_id, stats_text)
    finally:
        conn.close()


def show_my_orders(chat_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, marketplace, warehouse, loading_date FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE phone LIKE %s ORDER BY id DESC LIMIT 10",
                (f'%{chat_id}%',)
            )
            sender_orders = cur.fetchall()
            
            cur.execute(
                "SELECT id, marketplace, warehouse, loading_date, arrival_date FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE phone LIKE %s ORDER BY id DESC LIMIT 10",
                (f'%{chat_id}%',)
            )
            carrier_orders = cur.fetchall()
            
            if not sender_orders and not carrier_orders:
                send_message(
                    chat_id,
                    "📭 <b>У вас пока нет заявок</b>\n\nСоздайте заявку через главное меню, выбрав роль отправителя или перевозчика."
                )
                return
            
            message_parts = []
            keyboard_buttons = []
            
            if sender_orders:
                message_parts.append("📦 <b>Ваши заявки отправителя:</b>\n")
                for order in sender_orders:
                    message_parts.append(
                        f"#{order['id']} - {order.get('marketplace', '-')} → {order.get('warehouse', '-')} ({order.get('loading_date', '-')})\n"
                    )
                    keyboard_buttons.append([{
                        'text': f"🗑️ Удалить #{order['id']}",
                        'callback_data': f"delete_order_{order['id']}"
                    }])
            
            if carrier_orders:
                message_parts.append("\n🚚 <b>Ваши заявки перевозчика:</b>\n")
                for order in carrier_orders:
                    loading = order.get('loading_date', '-')
                    arrival = order.get('arrival_date', '-')
                    message_parts.append(
                        f"#{order['id']} - {order.get('marketplace', '-')} → {order.get('warehouse', '-')} ({loading} - {arrival})\n"
                    )
                    keyboard_buttons.append([{
                        'text': f"🗑️ Удалить #{order['id']}",
                        'callback_data': f"delete_order_{order['id']}"
                    }])
            
            send_message(
                chat_id,
                ''.join(message_parts),
                {'inline_keyboard': keyboard_buttons} if keyboard_buttons else None
            )
    finally:
        conn.close()


def delete_user_order(chat_id: int, order_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE id = %s AND chat_id = %s",
                (order_id, chat_id)
            )
            
            if cur.fetchone():
                cur.execute(
                    "DELETE FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE id = %s AND chat_id = %s",
                    (order_id, chat_id)
                )
                conn.commit()
                send_message(chat_id, f"✅ Заявка #{order_id} удалена")
                return
            
            cur.execute(
                "SELECT id FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE id = %s AND chat_id = %s",
                (order_id, chat_id)
            )
            
            if cur.fetchone():
                cur.execute(
                    "DELETE FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE id = %s AND chat_id = %s",
                    (order_id, chat_id)
                )
                conn.commit()
                send_message(chat_id, f"✅ Заявка #{order_id} удалена")
                return
            
            send_message(chat_id, f"❌ Заявка #{order_id} не найдена или вы не являетесь её владельцем")
    finally:
        conn.close()


def notify_about_new_order(order_id: int, order_type: str, data: Dict[str, Any]):
    if not ADMIN_CHAT_ID:
        return
    
    if order_type == 'sender':
        message = (
            f"🆕 <b>Новая заявка отправителя #{order_id}</b>\n\n"
            f"🏪 Маркетплейс: {data.get('marketplace', '-')}\n"
            f"📍 Склад: {data.get('warehouse')}\n"
            f"🏠 Адрес: {data.get('loading_address')}\n"
            f"📅 Дата: {data.get('loading_date')} {data.get('loading_time')}\n"
            f"📦 Паллеты: {data.get('pallet_quantity', 0)}\n"
            f"📦 Коробки: {data.get('box_quantity', 0)}\n"
            f"👤 Отправитель: {data.get('sender_name')}\n"
            f"📱 Телефон: {data.get('phone')}"
        )
    else:
        message = (
            f"🆕 <b>Новая заявка перевозчика #{order_id}</b>\n\n"
            f"🏪 Маркетплейс: {data.get('marketplace', '-')}\n"
            f"📍 Склад: {data.get('warehouse')}\n"
            f"🚗 Авто: {data.get('car_brand')} {data.get('car_model')}\n"
            f"🔢 Номер: {data.get('license_plate')}\n"
            f"📦 Вместимость: {data.get('pallet_capacity', 0)} паллет, {data.get('box_capacity', 0)} коробок\n"
            f"👤 Водитель: {data.get('driver_name')}\n"
            f"📱 Телефон: {data.get('phone')}\n"
            f"📅 Погрузка: {data.get('loading_date', '-')}\n"
            f"📅 Прибытие: {data.get('arrival_date', '-')}"
        )
    
    send_message(int(ADMIN_CHAT_ID), message)


def ask_notification_settings(chat_id: int, user_type: str, data: Dict[str, Any]):
    if user_type == 'sender':
        text = (
            "🔔 <b>Настройка уведомлений</b>\n\n"
            "Хотите получать уведомления о перевозчиках?\n\n"
            "• <b>Да, о всех</b> - все новые перевозчики\n"
            "• Укажите склад - только перевозчики на ваш склад"
        )
    else:
        text = (
            "🔔 <b>Настройка уведомлений</b>\n\n"
            "Хотите получать уведомления об отправителях?\n\n"
            "• <b>Да, о всех</b> - все новые отправители\n"
            "• Укажите склад - только отправители на этот склад"
        )
    
    keyboard = {
        'keyboard': [
            [{'text': '✅ Да, о всех'}],
            [{'text': f"📍 Только {data.get('warehouse', 'мой склад')}"}],
            [{'text': '❌ Нет, не нужны'}]
        ],
        'resize_keyboard': True,
        'one_time_keyboard': True
    }
    
    user_states[chat_id] = {
        'step': 'setup_notifications',
        'data': {'user_type': user_type, 'warehouse': data.get('warehouse')},
        'last_activity': time.time()
    }
    
    send_message(chat_id, text, keyboard)


def handle_notification_setup(chat_id: int, text: str, data: Dict[str, Any]):
    user_type = data.get('user_type')
    warehouse = data.get('warehouse')
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor() as cur:
            if 'да' in text.lower() and 'всех' in text.lower():
                cur.execute(
                    """
                    INSERT INTO t_p52349012_telegram_bot_creatio.user_subscriptions
                    (chat_id, user_type, subscription_type, warehouse_filter)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (chat_id, user_type, 'all', None)
                )
                send_message(
                    chat_id,
                    f"✅ Вы подписаны на все новые заявки!\n\nВведите /start для создания новой заявки",
                    {'remove_keyboard': True}
                )
            elif 'только' in text.lower() or warehouse:
                target_warehouse = warehouse if 'только' in text.lower() else text
                cur.execute(
                    """
                    INSERT INTO t_p52349012_telegram_bot_creatio.user_subscriptions
                    (chat_id, user_type, subscription_type, warehouse_filter)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (chat_id, user_type, 'warehouse', target_warehouse)
                )
                send_message(
                    chat_id,
                    f"✅ Вы подписаны на заявки по складу: {target_warehouse}\n\nВведите /start для создания новой заявки",
                    {'remove_keyboard': True}
                )
            else:
                send_message(
                    chat_id,
                    "❌ Подписка на уведомления отключена\n\nВведите /start для создания новой заявки",
                    {'remove_keyboard': True}
                )
            
            conn.commit()
            
            del user_states[chat_id]
    
    finally:
        conn.close()


def send_notifications_to_subscribers(order_id: int, order_type: str, data: Dict[str, Any]):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            target_user_type = 'carrier' if order_type == 'sender' else 'sender'
            warehouse = data.get('warehouse', '')
            
            warehouse_norm = normalize_warehouse(warehouse)
            cur.execute(
                """
                SELECT DISTINCT us.chat_id, us.warehouse_filter 
                FROM t_p52349012_telegram_bot_creatio.user_subscriptions us
                WHERE us.user_type = %s
                AND (us.subscription_type = 'all' 
                     OR (us.subscription_type = 'warehouse' 
                         AND (us.warehouse_filter = %s 
                              OR %s = ANY(SELECT normalize_warehouse(us.warehouse_filter)))))
                """,
                (target_user_type, warehouse, warehouse_norm)
            )
            
            subscribers = cur.fetchall()
            
            if order_type == 'sender':
                message = (
                    f"🆕 <b>Новая заявка отправителя #{order_id}</b>\n\n"
                    f"🏪 Маркетплейс: {data.get('marketplace', '-')}\n"
                    f"📍 Склад: {data.get('warehouse')}\n"
                    f"📅 Дата: {data.get('loading_date')} {data.get('loading_time')}\n"
                    f"📦 Груз: {data.get('pallet_quantity', 0)} паллет, {data.get('box_quantity', 0)} коробок\n"
                    f"💵 Ставка: {data.get('rate', '-')} руб.\n"
                    f"👤 Отправитель: {data.get('sender_name')}\n"
                    f"📱 Телефон: {data.get('phone')}"
                )
            else:
                message = (
                    f"🆕 <b>Новая заявка перевозчика #{order_id}</b>\n\n"
                    f"🏪 Маркетплейс: {data.get('marketplace', '-')}\n"
                    f"📍 Склад: {data.get('warehouse')}\n"
                    f"🚗 Авто: {data.get('car_brand')} {data.get('car_model')}\n"
                    f"📦 Вместимость: {data.get('pallet_capacity', 0)} паллет, {data.get('box_capacity', 0)} коробок\n"
                    f"🚚 Гидроборт: {data.get('hydroboard', '-')}\n"
                    f"👤 Водитель: {data.get('driver_name')}\n"
                    f"📱 Телефон: {data.get('phone')}"
                )
            
            for subscriber in subscribers:
                try:
                    send_message(subscriber['chat_id'], message)
                except:
                    pass
    
    finally:
        conn.close()


def find_matching_orders_by_date(order_id: int, order_type: str, data: Dict[str, Any]):
    """
    Автоматически подбирает заявки с совпадающими датами:
    - Для отправителя ищет перевозчиков с такой же датой погрузки
    - Для перевозчика ищет отправителей с совпадающей датой
    """
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if order_type == 'sender':
                # Отправитель создал заявку - ищем перевозчиков с такой же датой погрузки
                loading_date = data.get('loading_date')
                warehouse = data.get('warehouse')
                marketplace = data.get('marketplace')
                
                if not loading_date:
                    return
                
                warehouse_norm = normalize_warehouse(warehouse)
                cur.execute(
                    """
                    SELECT id, phone, driver_name, car_brand, car_model, 
                           pallet_capacity, box_capacity, loading_date, arrival_date, hydroboard, warehouse
                    FROM t_p52349012_telegram_bot_creatio.carrier_orders
                    WHERE loading_date = %s
                    AND (warehouse_normalized = %s OR warehouse = %s)
                    AND marketplace = %s
                    ORDER BY id DESC
                    LIMIT 5
                    """,
                    (loading_date, warehouse_norm, warehouse, marketplace)
                )
                
                matches = cur.fetchall()
                
                if matches:
                    # Отправляем отправителю список подходящих перевозчиков
                    sender_phone = data.get('phone', '').replace('+', '')
                    if sender_phone.isdigit():
                        sender_chat_id = int(sender_phone) if len(sender_phone) > 9 else None
                        
                        if sender_chat_id:
                            message = f"🎯 <b>Найдены подходящие перевозчики для вашей заявки #{order_id}!</b>\n\n"
                            message += f"📅 Дата погрузки: {loading_date}\n"
                            message += f"📍 Склад: {warehouse}\n\n"
                            
                            for i, match in enumerate(matches, 1):
                                message += (
                                    f"<b>{i}. {match['driver_name']}</b>\n"
                                    f"🚗 {match['car_brand']} {match['car_model']}\n"
                                    f"📦 Вместимость: {match['pallet_capacity']} паллет, {match['box_capacity']} коробок\n"
                                    f"🚚 Гидроборт: {match.get('hydroboard', '-')}\n"
                                    f"📱 Телефон: {match['phone']}\n"
                                    f"📅 Прибытие на склад: {match.get('arrival_date', '-')}\n\n"
                                )
                            
                            try:
                                send_message(sender_chat_id, message)
                            except:
                                pass
                    
                    # Отправляем перевозчикам уведомление о новом подходящем отправителе
                    for match in matches:
                        carrier_phone = match['phone'].replace('+', '')
                        if carrier_phone.isdigit():
                            carrier_chat_id = int(carrier_phone) if len(carrier_phone) > 9 else None
                            
                            if carrier_chat_id:
                                carrier_message = (
                                    f"🎯 <b>Найдена подходящая заявка отправителя #{order_id}!</b>\n\n"
                                    f"📅 Дата погрузки: {loading_date}\n"
                                    f"📍 Склад: {warehouse}\n"
                                    f"🏪 Маркетплейс: {marketplace}\n"
                                    f"📦 Груз: {data.get('pallet_quantity', 0)} паллет, {data.get('box_quantity', 0)} коробок\n"
                                    f"💵 Ставка: {data.get('rate', '-')} руб.\n"
                                    f"👤 Отправитель: {data.get('sender_name')}\n"
                                    f"📱 Телефон: {data.get('phone')}\n"
                                    f"🏠 Адрес: {data.get('loading_address')}"
                                )
                                
                                try:
                                    send_message(carrier_chat_id, carrier_message)
                                except:
                                    pass
            
            else:
                # Перевозчик создал заявку - ищем отправителей с подходящей датой
                loading_date = data.get('loading_date')
                warehouse = data.get('warehouse')
                marketplace = data.get('marketplace')
                
                if not loading_date:
                    return
                
                warehouse_norm = normalize_warehouse(warehouse)
                cur.execute(
                    """
                    SELECT id, phone, sender_name, loading_address, 
                           pallet_quantity, box_quantity, loading_date, loading_time, rate, warehouse
                    FROM t_p52349012_telegram_bot_creatio.sender_orders
                    WHERE loading_date = %s
                    AND (warehouse_normalized = %s OR warehouse = %s)
                    AND marketplace = %s
                    ORDER BY id DESC
                    LIMIT 5
                    """,
                    (loading_date, warehouse_norm, warehouse, marketplace)
                )
                
                matches = cur.fetchall()
                
                if matches:
                    # Отправляем перевозчику список подходящих отправителей
                    carrier_phone = data.get('phone', '').replace('+', '')
                    if carrier_phone.isdigit():
                        carrier_chat_id = int(carrier_phone) if len(carrier_phone) > 9 else None
                        
                        if carrier_chat_id:
                            message = f"🎯 <b>Найдены подходящие отправители для вашей заявки #{order_id}!</b>\n\n"
                            message += f"📅 Дата погрузки: {loading_date}\n"
                            message += f"📍 Склад: {warehouse}\n\n"
                            
                            for i, match in enumerate(matches, 1):
                                message += (
                                    f"<b>{i}. {match['sender_name']}</b>\n"
                                    f"📦 Груз: {match['pallet_quantity']} паллет, {match['box_quantity']} коробок\n"
                                    f"💵 Ставка: {match.get('rate', '-')} руб.\n"
                                    f"🏠 Адрес: {match['loading_address']}\n"
                                    f"📱 Телефон: {match['phone']}\n"
                                    f"🕐 Время погрузки: {match.get('loading_time', '-')}\n\n"
                                )
                            
                            try:
                                send_message(carrier_chat_id, message)
                            except:
                                pass
                    
                    # Отправляем отправителям уведомление о новом подходящем перевозчике
                    for match in matches:
                        sender_phone = match['phone'].replace('+', '')
                        if sender_phone.isdigit():
                            sender_chat_id = int(sender_phone) if len(sender_phone) > 9 else None
                            
                            if sender_chat_id:
                                sender_message = (
                                    f"🎯 <b>Найдена подходящая заявка перевозчика #{order_id}!</b>\n\n"
                                    f"📅 Дата погрузки: {loading_date}\n"
                                    f"📍 Склад: {warehouse}\n"
                                    f"🏪 Маркетплейс: {marketplace}\n"
                                    f"🚗 Авто: {data.get('car_brand')} {data.get('car_model')}\n"
                                    f"📦 Вместимость: {data.get('pallet_capacity', 0)} паллет, {data.get('box_capacity', 0)} коробок\n"
                                    f"🚚 Гидроборт: {data.get('hydroboard', '-')}\n"
                                    f"👤 Водитель: {data.get('driver_name')}\n"
                                    f"📱 Телефон: {data.get('phone')}\n"
                                    f"📅 Прибытие на склад: {data.get('arrival_date', '-')}"
                                )
                                
                                try:
                                    send_message(sender_chat_id, sender_message)
                                except:
                                    pass
    
    finally:
        conn.close()


def set_user_limit(chat_id: int, limit: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.user_limits (chat_id, daily_order_limit)
                VALUES (%s, %s)
                ON CONFLICT (chat_id) 
                DO UPDATE SET daily_order_limit = %s, updated_at = CURRENT_TIMESTAMP
                """,
                (chat_id, limit, limit)
            )
            conn.commit()
    finally:
        conn.close()


def show_security_logs(chat_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT chat_id, event_type, details, severity, created_at
                FROM t_p52349012_telegram_bot_creatio.security_logs
                ORDER BY created_at DESC
                LIMIT 20
            """)
            
            logs = cur.fetchall()
            
            if not logs:
                send_message(chat_id, "📋 Нет записей в логах безопасности")
                return
            
            message = "🔒 <b>ЛОГИ БЕЗОПАСНОСТИ (последние 20)</b>\n\n"
            
            for log in logs:
                severity_emoji = {
                    'low': '🟢',
                    'medium': '🟡',
                    'high': '🔴'
                }.get(log['severity'], '⚪')
                
                time_str = log['created_at'].strftime('%d.%m %H:%M')
                message += (
                    f"{severity_emoji} <code>{log['chat_id']}</code> - {log['event_type']}\n"
                    f"   {log['details']}\n"
                    f"   ⏰ {time_str}\n\n"
                )
            
            cur.execute("""
                SELECT event_type, COUNT(*) as cnt
                FROM t_p52349012_telegram_bot_creatio.security_logs
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY event_type
                ORDER BY cnt DESC
                LIMIT 5
            """)
            
            stats = cur.fetchall()
            
            if stats:
                message += "\n📊 <b>Статистика за 24 часа:</b>\n"
                for stat in stats:
                    message += f"• {stat['event_type']}: {stat['cnt']}\n"
            
            send_message(chat_id, message)
    finally:
        conn.close()


def show_blocked_users(chat_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT ab.chat_id, ab.reason, ab.blocked_at, ab.is_reviewed
                FROM t_p52349012_telegram_bot_creatio.auto_blocked_users ab
                ORDER BY ab.blocked_at DESC
                LIMIT 20
            """)
            
            blocked = cur.fetchall()
            
            if not blocked:
                send_message(chat_id, "👥 Нет заблокированных пользователей")
                return
            
            message = "🚫 <b>ЗАБЛОКИРОВАННЫЕ ПОЛЬЗОВАТЕЛИ</b>\n\n"
            
            for user in blocked:
                review_status = "✅ Проверено" if user['is_reviewed'] else "⏳ Ожидает проверки"
                time_str = user['blocked_at'].strftime('%d.%m.%Y %H:%M')
                
                message += (
                    f"👤 Chat ID: <code>{user['chat_id']}</code>\n"
                    f"📋 Причина: {user['reason']}\n"
                    f"⏰ Заблокирован: {time_str}\n"
                    f"🔍 Статус: {review_status}\n\n"
                )
            
            message += "\n💡 Для разблокировки отправьте команду:\n"
            message += "<code>/unblock CHAT_ID</code>"
            
            send_message(chat_id, message)
    finally:
        conn.close()


def delete_order_admin(chat_id: int, order_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE id = %s",
                (order_id,)
            )
            
            if cur.rowcount == 0:
                cur.execute(
                    "DELETE FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE id = %s",
                    (order_id,)
                )
            
            conn.commit()
            
            if cur.rowcount > 0:
                send_message(chat_id, f"✅ Заявка #{order_id} удалена администратором")
            else:
                send_message(chat_id, f"❌ Заявка #{order_id} не найдена")
    finally:
        conn.close()


def unblock_user(admin_chat_id: int, target_chat_id: int):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM t_p52349012_telegram_bot_creatio.blocked_users WHERE chat_id = %s",
                (target_chat_id,)
            )
            
            cur.execute(
                """
                UPDATE t_p52349012_telegram_bot_creatio.auto_blocked_users
                SET is_reviewed = TRUE, reviewed_by_admin = TRUE
                WHERE chat_id = %s
                """,
                (target_chat_id,)
            )
            
            conn.commit()
            
            send_message(admin_chat_id, f"✅ Пользователь {target_chat_id} разблокирован")
            
            try:
                send_message(target_chat_id, "✅ Ваш аккаунт разблокирован администратором. Введите /start для продолжения работы.")
            except:
                pass
    finally:
        conn.close()