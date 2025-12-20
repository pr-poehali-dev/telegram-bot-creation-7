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
PDF_FUNCTION_URL = 'https://functions.poehali.dev/a68807d2-57ae-4e99-b9e2-44b1dcfcc5b6'

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
TELEGRAM_IPS = ['149.154.160.0/20', '91.108.4.0/22', '185.178.208.0/22']


def normalize_warehouse(warehouse: str) -> str:
    """Нормализует название склада для fuzzy matching"""
    if not warehouse:
        return ''
    
    normalized = warehouse.lower().strip()
    normalized = ' '.join(normalized.split())
    
    replacements = {
        'коледино': 'каледино',
        'электросталь': 'електросталь',
        'подольск': 'падольск',
        'щелково': 'щолково',
        'чехов': 'чихов',
        'е': 'е',
        'ё': 'е'
    }
    
    for wrong, correct in replacements.items():
        normalized = normalized.replace(wrong, correct)
    
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


def get_admin_permissions(chat_id: int) -> Dict[str, bool]:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT ba.role, ap.*
                FROM t_p52349012_telegram_bot_creatio.bot_admins ba
                LEFT JOIN t_p52349012_telegram_bot_creatio.admin_permissions ap ON ba.id = ap.admin_id
                WHERE ba.chat_id = %s AND ba.is_active = true
            """, (chat_id,))
            result = cur.fetchone()
            
            if not result:
                return None
            
            role = result.get('role', 'viewer')
            
            if role == 'owner':
                return {
                    'role': 'owner',
                    'can_view_stats': True,
                    'can_view_orders': True,
                    'can_remove_orders': True,
                    'can_manage_users': True,
                    'can_block_users': True,
                    'can_manage_admins': True,
                    'can_view_security_logs': True
                }
            
            return {
                'role': role,
                'can_view_stats': result.get('can_view_stats', True),
                'can_view_orders': result.get('can_view_orders', True),
                'can_remove_orders': result.get('can_remove_orders', False),
                'can_manage_users': result.get('can_manage_users', False),
                'can_block_users': result.get('can_block_users', False),
                'can_manage_admins': result.get('can_manage_admins', False),
                'can_view_security_logs': result.get('can_view_security_logs', False)
            }
    except:
        return None
    finally:
        conn.close()


def is_admin(chat_id: int) -> bool:
    perms = get_admin_permissions(chat_id)
    return perms is not None


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


def get_user_templates(chat_id: int) -> List[Dict[str, Any]]:
    """Получить все шаблоны пользователя"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, template_name, order_type, template_data FROM t_p52349012_telegram_bot_creatio.order_templates WHERE chat_id = %s ORDER BY created_at DESC",
                (chat_id,)
            )
            return cur.fetchall()
    except:
        return []
    finally:
        conn.close()


def save_template(chat_id: int, template_name: str, order_type: str, data: Dict[str, Any]):
    """Сохранить шаблон заявки"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            import json
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.order_templates (chat_id, template_name, order_type, template_data)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (chat_id, template_name) DO UPDATE SET template_data = EXCLUDED.template_data, order_type = EXCLUDED.order_type
                """,
                (chat_id, template_name, order_type, json.dumps(data))
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"[ERROR] save_template failed: {str(e)}")
        return False
    finally:
        conn.close()


def load_template(template_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
    """Загрузить шаблон по ID"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT template_data, order_type FROM t_p52349012_telegram_bot_creatio.order_templates WHERE id = %s AND chat_id = %s",
                (template_id, chat_id)
            )
            result = cur.fetchone()
            if result:
                return {'data': result['template_data'], 'type': result['order_type']}
            return None
    except:
        return None
    finally:
        conn.close()


def delete_template(chat_id: int, template_id: int) -> bool:
    """Удалить шаблон по ID"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM t_p52349012_telegram_bot_creatio.order_templates WHERE id = %s AND chat_id = %s",
                (template_id, chat_id)
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        print(f"[ERROR] delete_template failed: {str(e)}")
        return False
    finally:
        conn.close()


def show_templates_management(chat_id: int):
    """Показать управление шаблонами"""
    templates = get_user_templates(chat_id)
    
    if not templates:
        send_message(
            chat_id,
            "📭 <b>У вас пока нет сохранённых шаблонов</b>\n\n"
            "Создайте заявку отправителя или перевозчика и нажмите 'Сохранить как шаблон'.\n\n"
            "Введите /start для создания новой заявки."
        )
        return
    
    message = "💾 <b>Ваши шаблоны:</b>\n\n"
    buttons = []
    
    for i, template in enumerate(templates):
        template_id = template['id']
        template_name = template['template_name']
        order_type = template['order_type']
        emoji = '📦' if order_type == 'sender' else '🚚'
        order_type_ru = 'Отправитель' if order_type == 'sender' else 'Перевозчик'
        
        message += f"{emoji} <b>{template_name}</b>\n"
        message += f"   Тип: {order_type_ru}\n\n"
        
        buttons.append([
            {'text': f'✅ Использовать', 'callback_data': f'use_template_{template_id}'}
        ])
        buttons.append([
            {'text': f'🗑 Удалить', 'callback_data': f'delete_template_{template_id}'}
        ])
        
        if i < len(templates) - 1:
            buttons.append([{'text': '—————————', 'callback_data': 'ignore'}])
    
    message += "💡 Выберите действие для нужного шаблона"
    
    send_message(
        chat_id,
        message,
        {'inline_keyboard': buttons}
    )


def show_main_menu(chat_id: int):
    """Показать главное меню выбора услуги"""
    user_states[chat_id] = {'step': 'choose_service', 'data': {}, 'last_activity': time.time()}
    
    templates = get_user_templates(chat_id)
    keyboard_buttons = [
        [{'text': '📦 Отправитель'}],
        [{'text': '🚚 Перевозчик'}],
        [{'text': '📋 Мои заявки'}]
    ]
    
    if templates:
        keyboard_buttons.append([{'text': '💾 Мои шаблоны'}])
    
    send_message(
        chat_id,
        "👋 <b>Добро пожаловать!</b>\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• Заявки отправителей удаляются через 5 дней после даты поставки\n"
        "• Сохраняйте скрины переписок\n"
        "• Сверяйте данные авто с заявкой\n\n"
        "<b>Выберите услугу:</b>",
        {
            'keyboard': keyboard_buttons,
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
    )


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
        print(f"Request from IP: {source_ip}")
        
        # Временно отключено для отладки
        # if not is_telegram_request(source_ip):
        #     return {
        #         'statusCode': 403,
        #         'headers': {'Content-Type': 'application/json'},
        #         'body': json.dumps({'error': 'Forbidden'}),
        #         'isBase64Encoded': False
        #     }
        
        body_data = json.loads(event.get('body', '{}'))
        print(f"Body data: {json.dumps(body_data)[:500]}")
        
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
        
        username = message.get('from', {}).get('username', 'unknown')
        process_message(chat_id, text, username)
        
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


def send_label_to_user(chat_id: int, order_id: int, order_type: str, label_size: str):
    try:
        response = requests.post(
            PDF_FUNCTION_URL,
            json={'order_id': order_id, 'order_type': order_type, 'label_size': label_size},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            pdf_base64 = result.get('pdf')
            
            if pdf_base64:
                import base64
                pdf_bytes = base64.b64decode(pdf_base64)
                send_document(chat_id, pdf_bytes, f'label_{order_id}.pdf', f'📄 Термоэтикетка для заявки #{order_id}')
                return True
            else:
                print(f"[ERROR] No PDF in response: {result}")
                return False
        else:
            print(f"[ERROR] PDF generation failed: status={response.status_code}, body={response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] send_label_to_user failed: {str(e)}")
        return False


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
    if callback_data == 'ignore':
        return
    
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
    
    if callback_data.startswith('set_role_'):
        role = callback_data.replace('set_role_', '')
        target_admin_id = state.get('target_admin_id')
        
        if not target_admin_id:
            send_message(chat_id, "❌ Ошибка: ID пользователя не найден")
            return
        
        role_permissions = {
            'admin': {
                'can_view_stats': True,
                'can_view_orders': True,
                'can_remove_orders': True,
                'can_manage_users': True,
                'can_block_users': True,
                'can_manage_admins': False,
                'can_view_security_logs': True
            },
            'moderator': {
                'can_view_stats': True,
                'can_view_orders': True,
                'can_remove_orders': True,
                'can_manage_users': False,
                'can_block_users': True,
                'can_manage_admins': False,
                'can_view_security_logs': False
            },
            'viewer': {
                'can_view_stats': True,
                'can_view_orders': True,
                'can_remove_orders': False,
                'can_manage_users': False,
                'can_block_users': False,
                'can_manage_admins': False,
                'can_view_security_logs': False
            }
        }
        
        perms = role_permissions.get(role, role_permissions['viewer'])
        
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO t_p52349012_telegram_bot_creatio.bot_admins (chat_id, username, role, is_active) VALUES (%s, %s, %s, true) RETURNING id",
                    (target_admin_id, f"user_{target_admin_id}", role)
                )
                admin_id = cur.fetchone()[0]
                
                cur.execute(
                    """
                    INSERT INTO t_p52349012_telegram_bot_creatio.admin_permissions 
                    (admin_id, can_view_stats, can_view_orders, can_remove_orders, can_manage_users, can_block_users, can_manage_admins, can_view_security_logs, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (admin_id, perms['can_view_stats'], perms['can_view_orders'], perms['can_remove_orders'], perms['can_manage_users'], perms['can_block_users'], perms['can_manage_admins'], perms['can_view_security_logs'])
                )
                
                conn.commit()
                
                role_names = {'admin': '⚡️ Администратор', 'moderator': '🛡 Модератор', 'viewer': '👁 Наблюдатель'}
                send_message(
                    chat_id,
                    f"✅ <b>Администратор добавлен!</b>\n\n"
                    f"Chat ID: <code>{target_admin_id}</code>\n"
                    f"Роль: {role_names.get(role, role)}\n\n"
                    f"Пользователь может использовать команду /admin для входа в админ-панель."
                )
                
                log_security_event(chat_id, 'admin_added', f'Добавлен новый админ {target_admin_id} с ролью {role}', 'high')
        finally:
            conn.close()
        
        if 'target_admin_id' in state:
            del state['target_admin_id']
        if 'step' in state:
            del state['step']
        
        return
    
    elif callback_data == 'cancel_add_admin':
        if 'target_admin_id' in state:
            del state['target_admin_id']
        if 'step' in state:
            del state['step']
        send_message(chat_id, "❌ Добавление администратора отменено")
        return
    
    elif callback_data == 'cancel_create':
        if chat_id in user_states:
            del user_states[chat_id]
        send_message(
            chat_id,
            "❌ Создание заявки отменено. Введите /start для начала",
            {'remove_keyboard': True}
        )
        return
    
    elif callback_data.startswith('use_template_'):
        template_id = int(callback_data.replace('use_template_', ''))
        template = load_template(template_id, chat_id)
        
        if not template:
            send_message(chat_id, "❌ Шаблон не найден")
            return
        
        template_data = template['data']
        template_type = template['type']
        
        data['type'] = template_type
        for key, value in template_data.items():
            data[key] = value
        
        state['step'] = 'show_preview'
        show_preview(chat_id, data)
        return
    
    elif callback_data.startswith('delete_template_'):
        template_id = int(callback_data.replace('delete_template_', ''))
        if delete_template(chat_id, template_id):
            send_message(chat_id, "✅ Шаблон удалён!")
            show_templates_management(chat_id)
        else:
            send_message(chat_id, "❌ Ошибка удаления шаблона")
        return
    
    if callback_data.startswith('edit_'):
        field = callback_data.replace('edit_', '')
        state['editing_field'] = field
        
        field_names = {
            'marketplace': 'маркетплейс',
            'warehouse': 'склад назначения',
            'loading_address': 'адрес погрузки',
            'loading_date': 'дату погрузки (ДД.ММ.ГГГГ)',
            'loading_time': 'время погрузки',
            'delivery_date': 'дату поставки на склад (ДД.ММ.ГГГГ)',
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
        elif field in ['loading_date', 'arrival_date', 'delivery_date']:
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
    
    elif callback_data == 'save_as_template':
        state['step'] = 'enter_template_name'
        send_message(
            chat_id,
            "💾 <b>Сохранение шаблона</b>\n\n"
            "Введите название для шаблона (от 3 до 50 символов):\n\n"
            "Например: 'Мой маршрут' или 'Доставка в Москву'",
            {'remove_keyboard': True}
        )
        return
    
    elif callback_data == 'confirm_create':
        print(f"[DEBUG] confirm_create pressed by chat_id={chat_id}, type={data.get('type')}")
        if data.get('type') == 'sender':
            print("[DEBUG] Calling save_sender_order...")
            save_sender_order(chat_id, data)
        else:
            print("[DEBUG] Calling save_carrier_order...")
            save_carrier_order(chat_id, data)
    
    elif callback_data.startswith('edit_order_'):
        parts = callback_data.replace('edit_order_', '').split('_')
        order_type = parts[0]
        order_id = int(parts[1])
        load_order_for_edit(chat_id, order_id, order_type)
        return
    
    elif callback_data.startswith('delete_order_'):
        parts = callback_data.replace('delete_order_', '').split('_')
        order_type = parts[0]
        order_id = int(parts[1])
        delete_user_order(chat_id, order_id, order_type)
        return
    
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
        if chat_id in user_states:
            del user_states[chat_id]
        send_message(
            chat_id,
            "❌ Заявка отменена. Введите /start для начала работы"
        )


def process_message(chat_id: int, text: str, username: str = 'unknown'):
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
    
    if text == '/add_admin':
        perms = get_admin_permissions(chat_id)
        if not perms or not perms.get('can_manage_admins'):
            send_message(chat_id, "❌ У вас нет прав для добавления администраторов")
            return
        
        state = user_states.get(chat_id, {'step': 'choose_service', 'data': {}})
        state['step'] = 'add_admin_chat_id'
        state['last_activity'] = time.time()
        user_states[chat_id] = state
        
        send_message(
            chat_id,
            "👤 <b>Добавление администратора</b>\n\n"
            "Отправьте мне Chat ID пользователя, которого хотите добавить.\n\n"
            "💡 <i>Подсказка:</i> Пользователь может узнать свой Chat ID командой /my_id"
        )
        return
    
    if text == '/admin':
        perms = get_admin_permissions(chat_id)
        if not perms:
            send_message(chat_id, "❌ У вас нет прав администратора")
            return
        
        admin_sessions[chat_id] = int(time.time())
        
        role_text = {
            'owner': '👑 Владелец',
            'admin': '⚡️ Администратор',
            'moderator': '🛡 Модератор',
            'viewer': '👁 Наблюдатель'
        }.get(perms.get('role', 'viewer'), '👁 Наблюдатель')
        
        buttons = []
        
        if perms.get('can_view_stats'):
            buttons.append([{'text': '📊 Статистика', 'callback_data': 'admin_stats'}])
            buttons.append([{'text': '📈 Еженедельный отчёт', 'callback_data': 'admin_weekly'}])
        
        if perms.get('can_view_security_logs'):
            buttons.append([{'text': '🔒 Логи безопасности', 'callback_data': 'admin_security_logs'}])
        
        if perms.get('can_block_users'):
            buttons.append([{'text': '🚫 Заблокированные', 'callback_data': 'admin_blocked_users'}])
        
        if perms.get('can_manage_users'):
            buttons.append([{'text': '⚙️ Установить лимит', 'callback_data': 'admin_set_limit'}])
        
        if perms.get('can_remove_orders'):
            buttons.append([{'text': '🗑️ Удалить заявку', 'callback_data': 'admin_delete'}])
            buttons.append([{'text': '🧹 Очистить старые заявки', 'callback_data': 'admin_cleanup'}])
        
        if perms.get('can_manage_admins'):
            buttons.append([{'text': '👥 Управление админами', 'callback_data': 'admin_manage_admins'}])
        
        buttons.append([{'text': '🏠 Выйти из админ-панели', 'callback_data': 'admin_exit'}])
        
        send_message(
            chat_id,
            f"🔧 <b>Админ-панель</b>\n\n"
            f"Ваша роль: {role_text}\n\n"
            f"Выберите действие:",
            {'inline_keyboard': buttons}
        )
        return
    
    if text == '/add_admin':
        if str(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "❌ Только владелец бота может добавлять администраторов")
            return
        
        user_states[chat_id] = {'step': 'add_admin_chat_id', 'data': {}, 'last_activity': time.time()}
        send_message(
            chat_id,
            "👤 <b>Добавление нового администратора</b>\n\n"
            "Отправьте Chat ID пользователя, которого хотите сделать администратором\n\n"
            "💡 Пользователь может узнать свой Chat ID командой /my_id"
        )
        return
    
    if text == '/list_admins':
        if str(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "❌ Доступно только владельцу бота")
            return
        
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT chat_id, username, is_active, added_at FROM t_p52349012_telegram_bot_creatio.bot_admins ORDER BY added_at DESC"
                )
                admins = cur.fetchall()
                
                if not admins:
                    send_message(chat_id, "📭 Список администраторов пуст")
                    return
                
                message_parts = ["👥 <b>Список администраторов:</b>\n"]
                for admin in admins:
                    status = "✅" if admin['is_active'] else "❌"
                    message_parts.append(
                        f"\n{status} @{admin.get('username', 'нет username')}\n"
                        f"   Chat ID: <code>{admin['chat_id']}</code>\n"
                        f"   Добавлен: {admin['added_at'].strftime('%d.%m.%Y %H:%M') if admin['added_at'] else 'неизвестно'}"
                    )
                
                send_message(chat_id, ''.join(message_parts))
        finally:
            conn.close()
        return
    
    if text.startswith('/remove_admin '):
        if str(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "❌ Только владелец бота может удалять администраторов")
            return
        
        parts = text.split(' ', 1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            send_message(chat_id, "❌ Неверный формат.\n\nИспользование: /remove_admin CHAT_ID")
            return
        
        target_chat_id = int(parts[1].strip())
        
        if target_chat_id == int(ADMIN_CHAT_ID):
            send_message(chat_id, "❌ Нельзя удалить владельца бота")
            return
        
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE t_p52349012_telegram_bot_creatio.bot_admins SET is_active = false WHERE chat_id = %s",
                    (target_chat_id,)
                )
                conn.commit()
                
                if cur.rowcount > 0:
                    send_message(chat_id, f"✅ Администратор {target_chat_id} деактивирован")
                    log_security_event(chat_id, 'admin_removed', f'Админ {target_chat_id} деактивирован', 'high')
                else:
                    send_message(chat_id, f"❌ Администратор с Chat ID {target_chat_id} не найден")
        finally:
            conn.close()
        return
    
    if text == '/my_id':
        send_message(
            chat_id,
            f"🆔 <b>Ваш Chat ID:</b> <code>{chat_id}</code>\n\n"
            f"Скопируйте это значение и отправьте владельцу бота для получения прав администратора"
        )
        return
    
    if text == '/start':
        user_states[chat_id] = {'step': 'choose_service', 'data': {}, 'last_activity': time.time()}
        
        templates = get_user_templates(chat_id)
        keyboard_buttons = [
            [{'text': '📦 Отправитель'}],
            [{'text': '🚚 Перевозчик'}],
            [{'text': '📋 Мои заявки'}]
        ]
        
        if templates:
            keyboard_buttons.append([{'text': '💾 Мои шаблоны'}])
        
        send_message(
            chat_id,
            "👋 <b>Добро пожаловать!</b>\n\n"
            "⚠️ <b>Важно:</b>\n"
            "• Сохраняйте скрины переписок\n"
            "• Сверяйте данные авто с заявкой\n"
            "• Будьте внимательны к деталям\n\n"
            "<b>Выберите услугу:</b>",
            {
                'keyboard': keyboard_buttons,
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
    
    if step == 'add_admin_chat_id':
        if not text.isdigit():
            send_message(chat_id, "❌ Неверный формат. Отправьте числовой Chat ID")
            return
        
        target_chat_id = int(text)
        
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM t_p52349012_telegram_bot_creatio.bot_admins WHERE chat_id = %s",
                    (target_chat_id,)
                )
                
                if cur.fetchone():
                    send_message(chat_id, f"ℹ️ Пользователь {target_chat_id} уже является администратором")
                    del state['step']
                else:
                    state['step'] = 'add_admin_role'
                    state['target_admin_id'] = target_chat_id
                    
                    send_message(
                        chat_id,
                        f"👤 <b>Выберите роль для администратора</b>\n\n"
                        f"Chat ID: <code>{target_chat_id}</code>\n\n"
                        f"<b>Доступные роли:</b>\n\n"
                        f"⚡️ <b>Администратор</b> — полный доступ кроме управления админами\n"
                        f"• Просмотр статистики и заявок\n"
                        f"• Удаление заявок\n"
                        f"• Управление пользователями\n"
                        f"• Блокировка пользователей\n"
                        f"• Просмотр логов безопасности\n\n"
                        f"🛡 <b>Модератор</b> — управление контентом\n"
                        f"• Просмотр статистики и заявок\n"
                        f"• Удаление заявок\n"
                        f"• Блокировка пользователей\n\n"
                        f"👁 <b>Наблюдатель</b> — только просмотр\n"
                        f"• Просмотр статистики и заявок",
                        {
                            'inline_keyboard': [
                                [{'text': '⚡️ Администратор', 'callback_data': 'set_role_admin'}],
                                [{'text': '🛡 Модератор', 'callback_data': 'set_role_moderator'}],
                                [{'text': '👁 Наблюдатель', 'callback_data': 'set_role_viewer'}],
                                [{'text': '❌ Отмена', 'callback_data': 'cancel_add_admin'}]
                            ]
                        }
                    )
                    
                    send_message(
                        target_chat_id,
                        f"🎉 <b>Вы стали администратором бота!</b>\n\n"
                        f"Теперь вы будете получать уведомления о всех новых заявках.\n"
                        f"Используйте /start для доступа к функциям бота."
                    )
                    
                    log_security_event(chat_id, 'admin_added', f'Новый админ добавлен: {target_chat_id}', 'high')
        finally:
            conn.close()
        
        del user_states[chat_id]
        return
    
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
        elif field in ['loading_date', 'arrival_date', 'delivery_date']:
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
    
    if step == 'enter_template_name':
        template_name = text.strip()
        
        if len(template_name) < 3:
            send_message(chat_id, "❌ Имя шаблона должно быть минимум 3 символа. Попробуйте ещё раз:")
            return
        
        if len(template_name) > 50:
            send_message(chat_id, "❌ Имя шаблона слишком длинное (макс 50 символов). Попробуйте ещё раз:")
            return
        
        order_type = data.get('type', 'sender')
        if save_template(chat_id, template_name, order_type, data):
            send_message(
                chat_id,
                f"✅ <b>Шаблон '{template_name}' сохранён!</b>\n\nТеперь вы можете найти его в разделе 'Мои шаблоны'."
            )
            show_preview(chat_id, data)
        else:
            send_message(
                chat_id,
                "❌ Ошибка сохранения шаблона. Попробуйте ещё раз или обратитесь к администратору."
            )
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
        elif 'мои заявки' in text.lower() or '📋' in text:
            show_my_orders(chat_id)
            return
        elif 'мои шаблоны' in text.lower() or '💾' in text:
            show_templates_management(chat_id)
            return
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
        send_message(chat_id, "🏠 <b>Укажите адрес ПОГРУЗКИ</b>\n\nНапример: г. Москва, ул. Ленина, д. 10")
    
    elif step == 'sender_loading_address':
        data['loading_address'] = text
        state['step'] = 'sender_loading_date'
        
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        send_message(
            chat_id,
            "📅 <b>Укажите дату ПОГРУЗКИ</b>",
            {
                'keyboard': [
                    [{'text': f"🔴 Сегодня ({today.strftime('%d.%m.%Y')})"}],
                    [{'text': f"🟢 Завтра ({tomorrow.strftime('%d.%m.%Y')})"}],
                    [{'text': 'Ввести дату'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'sender_loading_date':
        try:
            if 'сегодня' in text.lower() or '🔴' in text:
                loading_date = datetime.now()
            elif 'завтра' in text.lower() or '🟢' in text:
                loading_date = datetime.now() + timedelta(days=1)
            elif 'ввести' in text.lower():
                send_message(chat_id, "📅 <b>Введите дату ПОГРУЗКИ</b>\n\nФормат: ДД.ММ.ГГГГ\nНапример: 25.12.2025", {'remove_keyboard': True})
                return
            else:
                loading_date = datetime.strptime(text, '%d.%m.%Y')
            
            data['loading_date'] = loading_date.strftime('%Y-%m-%d')
            
            days_until = (loading_date - datetime.now()).days
            if days_until > 1:
                send_message(
                    chat_id,
                    f"⚠️ <b>Внимание!</b> Заявка будет автоматически удалена через 24 часа после указанной даты ПОГРУЗКИ.\n\n" +
                    f"Дата ПОГРУЗКИ: {loading_date.strftime('%d.%m.%Y')}\n" +
                    f"Заявка будет удалена: {(loading_date + timedelta(days=1)).strftime('%d.%m.%Y')}"
                )
            
            state['step'] = 'sender_loading_time'
            send_message(chat_id, "🕐 <b>Укажите время ПОГРУЗКИ</b>\n\nФормат: ЧЧ:ММ\nНапример: 14:30", {'remove_keyboard': True})
        except ValueError:
            send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
    
    elif step == 'sender_loading_time':
        import re
        time_pattern = r'^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$'
        if not re.match(time_pattern, text):
            send_message(chat_id, "❌ Неверный формат времени. Используйте ЧЧ:ММ (например: 14:30)")
            return
        data['loading_time'] = text
        state['step'] = 'sender_delivery_date'
        
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        send_message(
            chat_id,
            "📅 <b>Укажите дату ПОСТАВКИ на склад</b>",
            {
                'keyboard': [
                    [{'text': f"🔴 Сегодня ({today.strftime('%d.%m.%Y')})"}],
                    [{'text': f"🟢 Завтра ({tomorrow.strftime('%d.%m.%Y')})"}],
                    [{'text': 'Ввести дату'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'sender_pallet_quantity':
        data['pallet_quantity'] = int(text) if text.isdigit() else 0
        state['step'] = 'sender_box_quantity'
        send_message(chat_id, "📦 <b>Укажите количество коробок</b>\n\nНапример: 10\nИли 0, если нет коробок")
    
    elif step == 'sender_delivery_date':
        try:
            if 'сегодня' in text.lower() or '🔴' in text:
                delivery_date = datetime.now()
            elif 'завтра' in text.lower() or '🟢' in text:
                delivery_date = datetime.now() + timedelta(days=1)
            elif 'ввести' in text.lower():
                send_message(chat_id, "📅 <b>Введите дату ПОСТАВКИ на склад</b>\n\nФормат: ДД.ММ.ГГГГ\nНапример: 25.12.2025", {'remove_keyboard': True})
                return
            else:
                delivery_date = datetime.strptime(text, '%d.%m.%Y')
            
            data['delivery_date'] = delivery_date.strftime('%Y-%m-%d')
            state['step'] = 'sender_pallet_quantity'
            send_message(chat_id, "📦 <b>Укажите количество паллет</b>\n\nНапример: 5\nИли 0, если нет паллет", {'remove_keyboard': True})
        except ValueError:
            send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
    
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
            "📅 <b>Укажите желаемую дату ПОГРУЗКИ</b>\n\nВыберите из вариантов или введите дату вручную\nФормат: ДД.ММ.ГГГГ",
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
            state['step'] = 'show_preview'
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
            f"🏠 Адрес ПОГРУЗКИ: {data.get('loading_address', '-')}\n"
            f"📅 Дата ПОГРУЗКИ: {data.get('loading_date', '-')}\n"
            f"🕐 Время ПОГРУЗКИ: {data.get('loading_time', '-')}\n"
            f"📅 Дата ПОСТАВКИ: {data.get('delivery_date', '-')}\n"
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
                    {'text': '✏️ Дата погрузки', 'callback_data': 'edit_loading_date'}
                ],
                [
                    {'text': '✏️ Время', 'callback_data': 'edit_loading_time'},
                    {'text': '✏️ Дата ПОСТАВКИ', 'callback_data': 'edit_delivery_date'}
                ],
                [
                    {'text': '✏️ Паллеты', 'callback_data': 'edit_pallet_quantity'},
                    {'text': '✏️ Коробки', 'callback_data': 'edit_box_quantity'}
                ],
                [
                    {'text': '✏️ ФИО', 'callback_data': 'edit_sender_name'},
                    {'text': '✏️ Телефон', 'callback_data': 'edit_phone'}
                ],
                [
                    {'text': '✏️ Ставка', 'callback_data': 'edit_rate'}
                ],
                [
                    {'text': '💾 Сохранить как шаблон', 'callback_data': 'save_as_template'}
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
            f"📅 Дата ПОГРУЗКИ: {data.get('loading_date', '-')}\n"
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
                    {'text': '✏️ Дата ПОГРУЗКИ', 'callback_data': 'edit_loading_date'},
                    {'text': '✏️ Дата прибытия', 'callback_data': 'edit_arrival_date'}
                ],
                [
                    {'text': '💾 Сохранить как шаблон', 'callback_data': 'save_as_template'}
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
    try:
        print(f"[DEBUG] save_sender_order called for chat_id={chat_id}, data={data}")
        edit_mode = data.get('edit_mode', False)
        original_order_id = data.get('original_order_id')
        
        if edit_mode:
            send_message(chat_id, "⏳ Сохраняю изменения...")
        else:
            send_message(chat_id, "⏳ Создаю заявку...")
        
        if not edit_mode:
            user_limit = get_user_daily_limit(chat_id)
            orders_today = get_user_orders_today(chat_id)
            print(f"[DEBUG] user_limit={user_limit}, orders_today={orders_today}")
        
            if orders_today >= user_limit:
                log_security_event(chat_id, 'order_limit_exceeded', f'Попытка создать {orders_today + 1} заявку при лимите {user_limit}', 'medium')
                send_message(
                    chat_id,
                    f"❌ <b>Превышен лимит заявок</b>\n\nВы можете создать максимум {user_limit} заявок в день.\nПопробуйте завтра.",
                    {'remove_keyboard': True}
                )
                return
        
        print("[DEBUG] Connecting to database...")
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                warehouse_norm = normalize_warehouse(data.get('warehouse', ''))
                
                # Определяем тип груза на основе количества (только 'pallet' или 'box')
                pallet_qty = data.get('pallet_quantity', 0)
                box_qty = data.get('box_quantity', 0)
                if pallet_qty > 0:
                    cargo_type = 'pallet'
                else:
                    cargo_type = 'box'
                
                # Экранируем строки для SQL
                def escape_sql(value):
                    if value is None:
                        return 'NULL'
                    if isinstance(value, (int, float)):
                        return str(value)
                    return "'" + str(value).replace("'", "''") + "'"
                
                if edit_mode and original_order_id:
                    print(f"[DEBUG] Executing UPDATE query for order_id={original_order_id}...")
                    query = f"""
                        UPDATE t_p52349012_telegram_bot_creatio.sender_orders
                        SET loading_address = {escape_sql(data.get('loading_address'))},
                            warehouse = {escape_sql(data.get('warehouse'))},
                            cargo_type = {escape_sql(cargo_type)},
                            sender_name = {escape_sql(data.get('sender_name'))},
                            phone = {escape_sql(data.get('phone'))},
                            loading_date = {escape_sql(data.get('loading_date'))},
                            loading_time = {escape_sql(data.get('loading_time'))},
                            delivery_date = {escape_sql(data.get('delivery_date'))},
                            pallet_quantity = {data.get('pallet_quantity', 0)},
                            box_quantity = {data.get('box_quantity', 0)},
                            marketplace = {escape_sql(data.get('marketplace'))},
                            rate = {escape_sql(data.get('rate'))},
                            warehouse_normalized = {escape_sql(warehouse_norm)}
                        WHERE id = {original_order_id} AND chat_id = {chat_id}
                        RETURNING id
                    """
                    order_id = original_order_id
                else:
                    print(f"[DEBUG] Executing INSERT query...")
                    query = f"""
                        INSERT INTO t_p52349012_telegram_bot_creatio.sender_orders
                        (loading_address, warehouse, cargo_type, sender_name, phone, loading_date, loading_time, delivery_date, pallet_quantity, box_quantity, label_size, marketplace, chat_id, rate, warehouse_normalized)
                        VALUES ({escape_sql(data.get('loading_address'))}, {escape_sql(data.get('warehouse'))}, {escape_sql(cargo_type)}, {escape_sql(data.get('sender_name'))}, {escape_sql(data.get('phone'))}, {escape_sql(data.get('loading_date'))}, {escape_sql(data.get('loading_time'))}, {escape_sql(data.get('delivery_date'))}, {data.get('pallet_quantity', 0)}, {data.get('box_quantity', 0)}, '120x75', {escape_sql(data.get('marketplace'))}, {chat_id}, {escape_sql(data.get('rate'))}, {escape_sql(warehouse_norm)})
                        RETURNING id
                    """
                
                print(f"[DEBUG] Query: {query}")
                cur.execute(query)
                
                if not edit_mode:
                    print("[DEBUG] Fetching order_id...")
                    result = cur.fetchone()
                    print(f"[DEBUG] fetchone result: {result}, type: {type(result)}")
                    
                    if result is None:
                        raise Exception("INSERT query returned no result")
                    
                    order_id = result['id'] if isinstance(result, dict) else result[0]
                print(f"[DEBUG] Extracted order_id={order_id}")
                conn.commit()
                print(f"[DEBUG] Order {'updated' if edit_mode else 'created'} with id={order_id}")
                
                if edit_mode:
                    send_message(
                        chat_id,
                        f"✅ <b>Заявка #{order_id} обновлена!</b>\n\nИзменения сохранены."
                    )
                else:
                    delivery_date_str = data.get('delivery_date', '')
                    try:
                        from datetime import datetime, timedelta
                        delivery_date_obj = datetime.strptime(delivery_date_str, '%Y-%m-%d')
                        delete_date = delivery_date_obj + timedelta(days=5)
                        delete_date_str = delete_date.strftime('%d.%m.%Y')
                        auto_delete_warning = f"\n\n⏰ <b>Важно:</b> Заявка будет автоматически удалена {delete_date_str} (через 5 дней после даты поставки)"
                    except:
                        auto_delete_warning = "\n\n⏰ <b>Важно:</b> Заявка будет автоматически удалена через 5 дней после даты поставки на склад"
                    
                    send_message(
                        chat_id,
                        f"✅ <b>Заявка #{order_id} создана!</b>\n\nВаш груз добавлен в систему.{auto_delete_warning}"
                    )
                    
                    label_size = data.get('label_size', '120x75')
                    send_label_to_user(chat_id, order_id, 'sender', label_size)
                    notify_about_new_order(order_id, 'sender', data)
                send_notifications_to_subscribers(order_id, 'sender', data)
                find_matching_orders_by_date(order_id, 'sender', data)
                
                if chat_id in user_states:
                    del user_states[chat_id]
                
                show_main_menu(chat_id)
        
        finally:
            conn.close()
    
    except Exception as e:
        print(f"[ERROR] save_sender_order failed: {str(e)}")
        send_message(chat_id, f"❌ Ошибка создания заявки: {str(e)}\n\nПопробуйте ещё раз или обратитесь к администратору.")


def save_carrier_order(chat_id: int, data: Dict[str, Any]):
    try:
        print(f"[DEBUG] save_carrier_order called for chat_id={chat_id}, data={data}")
        edit_mode = data.get('edit_mode', False)
        original_order_id = data.get('original_order_id')
        
        if edit_mode:
            send_message(chat_id, "⏳ Сохраняю изменения...")
        else:
            send_message(chat_id, "⏳ Создаю заявку...")
        
        if not edit_mode:
            user_limit = get_user_daily_limit(chat_id)
            orders_today = get_user_orders_today(chat_id)
            print(f"[DEBUG] user_limit={user_limit}, orders_today={orders_today}")
        
            if orders_today >= user_limit:
                log_security_event(chat_id, 'order_limit_exceeded', f'Попытка создать {orders_today + 1} заявку при лимите {user_limit}', 'medium')
                send_message(
                    chat_id,
                    f"❌ <b>Превышен лимит заявок</b>\n\nВы можете создать максимум {user_limit} заявок в день.\nПопробуйте завтра.",
                    {'remove_keyboard': True}
                )
                return
        
        print("[DEBUG] Connecting to database...")
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                warehouse_norm = normalize_warehouse(data.get('warehouse', ''))
                
                # Определяем capacity_type на основе количества
                pallet_cap = data.get('pallet_capacity', 0)
                box_cap = data.get('box_capacity', 0)
                capacity_type = 'pallet' if pallet_cap > 0 else 'box'
                
                # Экранируем строки для SQL
                def escape_sql(value):
                    if value is None:
                        return 'NULL'
                    if isinstance(value, (int, float)):
                        return str(value)
                    return "'" + str(value).replace("'", "''") + "'"
                
                if edit_mode and original_order_id:
                    print(f"[DEBUG] Executing UPDATE query for order_id={original_order_id}...")
                    query = f"""
                        UPDATE t_p52349012_telegram_bot_creatio.carrier_orders
                        SET car_brand = {escape_sql(data.get('car_brand'))},
                            license_plate = {escape_sql(data.get('license_plate'))},
                            capacity_type = {escape_sql(capacity_type)},
                            driver_name = {escape_sql(data.get('driver_name'))},
                            phone = {escape_sql(data.get('phone'))},
                            warehouse = {escape_sql(data.get('warehouse'))},
                            car_model = {escape_sql(data.get('car_model'))},
                            pallet_capacity = {pallet_cap},
                            box_capacity = {box_cap},
                            marketplace = {escape_sql(data.get('marketplace'))},
                            loading_date = {escape_sql(data.get('loading_date'))},
                            arrival_date = {escape_sql(data.get('arrival_date'))},
                            hydroboard = {escape_sql(data.get('hydroboard'))},
                            warehouse_normalized = {escape_sql(warehouse_norm)}
                        WHERE id = {original_order_id} AND chat_id = {chat_id}
                        RETURNING id
                    """
                    order_id = original_order_id
                else:
                    print(f"[DEBUG] Executing INSERT query...")
                    query = f"""
                        INSERT INTO t_p52349012_telegram_bot_creatio.carrier_orders
                        (car_brand, license_plate, capacity_type, driver_name, phone, warehouse, car_model, pallet_capacity, box_capacity, marketplace, loading_date, arrival_date, hydroboard, chat_id, warehouse_normalized)
                        VALUES ({escape_sql(data.get('car_brand'))}, {escape_sql(data.get('license_plate'))}, {escape_sql(capacity_type)}, {escape_sql(data.get('driver_name'))}, {escape_sql(data.get('phone'))}, {escape_sql(data.get('warehouse'))}, {escape_sql(data.get('car_model'))}, {pallet_cap}, {box_cap}, {escape_sql(data.get('marketplace'))}, {escape_sql(data.get('loading_date'))}, {escape_sql(data.get('arrival_date'))}, {escape_sql(data.get('hydroboard'))}, {chat_id}, {escape_sql(warehouse_norm)})
                        RETURNING id
                    """
                
                print(f"[DEBUG] Query: {query}")
                cur.execute(query)
                
                if not edit_mode:
                    print("[DEBUG] Fetching order_id...")
                    result = cur.fetchone()
                    print(f"[DEBUG] fetchone result: {result}, type: {type(result)}")
                    
                    if result is None:
                        raise Exception("INSERT query returned no result")
                    
                    order_id = result['id'] if isinstance(result, dict) else result[0]
                print(f"[DEBUG] Extracted order_id={order_id}")
                conn.commit()
                print(f"[DEBUG] Order {'updated' if edit_mode else 'created'} with id={order_id}")
                
                if edit_mode:
                    send_message(
                        chat_id,
                        f"✅ <b>Заявка #{order_id} обновлена!</b>\n\nИзменения сохранены."
                    )
                else:
                    send_message(
                        chat_id,
                        f"✅ <b>Заявка #{order_id} создана!</b>\n\nОтправители получили уведомление о вашем предложении."
                    )
                    notify_about_new_order(order_id, 'carrier', data)
                send_notifications_to_subscribers(order_id, 'carrier', data)
                find_matching_orders_by_date(order_id, 'carrier', data)
                
                if chat_id in user_states:
                    del user_states[chat_id]
                
                show_main_menu(chat_id)
        
        finally:
            conn.close()
    
    except Exception as e:
        print(f"[ERROR] save_carrier_order failed: {str(e)}")
        send_message(chat_id, f"❌ Ошибка создания заявки: {str(e)}\n\nПопробуйте ещё раз или обратитесь к администратору.")


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
                WHERE delivery_date < CURRENT_DATE - INTERVAL '5 days'
            """)
            deleted_count = cur.rowcount
            conn.commit()
            
            send_message(chat_id, f"🧹 Удалено старых заявок отправителей: {deleted_count}")
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
                "SELECT id, marketplace, warehouse, loading_date FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE chat_id = %s ORDER BY id DESC LIMIT 10",
                (chat_id,)
            )
            sender_orders = cur.fetchall()
            
            cur.execute(
                "SELECT id, marketplace, warehouse, loading_date, arrival_date FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE chat_id = %s ORDER BY id DESC LIMIT 10",
                (chat_id,)
            )
            carrier_orders = cur.fetchall()
            
            if not sender_orders and not carrier_orders:
                send_message(
                    chat_id,
                    "📭 <b>У вас пока нет заявок</b>\n\nСоздайте заявку через главное меню, выбрав роль отправителя или перевозчика."
                )
                return
            
            if sender_orders:
                send_message(chat_id, "📦 <b>Ваши заявки отправителя:</b>")
                for order in sender_orders:
                    order_text = f"#{order['id']} - {order.get('marketplace', '-')} → {order.get('warehouse', '-')} ({order.get('loading_date', '-')})"
                    keyboard = {
                        'inline_keyboard': [
                            [
                                {'text': '✏️ Редактировать', 'callback_data': f"edit_order_sender_{order['id']}"}
                            ],
                            [
                                {'text': '🗑️ Удалить', 'callback_data': f"delete_order_sender_{order['id']}"}
                            ]
                        ]
                    }
                    send_message(chat_id, order_text, keyboard)
            
            if carrier_orders:
                send_message(chat_id, "🚚 <b>Ваши заявки перевозчика:</b>")
                for order in carrier_orders:
                    loading = order.get('loading_date', '-')
                    arrival = order.get('arrival_date', '-')
                    order_text = f"#{order['id']} - {order.get('marketplace', '-')} → {order.get('warehouse', '-')} ({loading} - {arrival})"
                    keyboard = {
                        'inline_keyboard': [
                            [
                                {'text': '✏️ Редактировать', 'callback_data': f"edit_order_carrier_{order['id']}"}
                            ],
                            [
                                {'text': '🗑️ Удалить', 'callback_data': f"delete_order_carrier_{order['id']}"}
                            ]
                        ]
                    }
                    send_message(chat_id, order_text, keyboard)
    finally:
        conn.close()


def delete_user_order(chat_id: int, order_id: int, order_type: str):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            table = 'sender_orders' if order_type == 'sender' else 'carrier_orders'
            cur.execute(
                f"DELETE FROM t_p52349012_telegram_bot_creatio.{table} WHERE id = %s AND chat_id = %s",
                (order_id, chat_id)
            )
            conn.commit()
            show_my_orders(chat_id)
    finally:
        conn.close()


def load_order_for_edit(chat_id: int, order_id: int, order_type: str):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if order_type == 'sender':
                cur.execute(
                    "SELECT * FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE id = %s AND chat_id = %s",
                    (order_id, chat_id)
                )
            else:
                cur.execute(
                    "SELECT * FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE id = %s AND chat_id = %s",
                    (order_id, chat_id)
                )
            
            order = cur.fetchone()
            if not order:
                send_message(chat_id, "❌ Заявка не найдена")
                return
            
            data = dict(order)
            data['type'] = order_type
            data['edit_mode'] = True
            data['original_order_id'] = order_id
            
            user_states[chat_id] = {
                'step': 'show_preview',
                'data': data,
                'last_activity': time.time()
            }
            
            show_preview(chat_id, data)
    finally:
        conn.close()


def notify_about_new_order(order_id: int, order_type: str, data: Dict[str, Any]):
    """Отправляет уведомления о новой заявке всем активным админам"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Получаем всех активных админов с включенными уведомлениями
            cur.execute("""
                SELECT ba.chat_id 
                FROM t_p52349012_telegram_bot_creatio.bot_admins ba
                LEFT JOIN t_p52349012_telegram_bot_creatio.notification_settings ns 
                ON ba.chat_id = ns.chat_id
                WHERE ba.is_active = true 
                AND (ns.notify_new_orders = true OR ns.notify_new_orders IS NULL)
            """)
            
            admins = cur.fetchall()
            
            if not admins and ADMIN_CHAT_ID:
                # Фоллбек на старый способ через переменную окружения
                admins = [{'chat_id': int(ADMIN_CHAT_ID)}]
            
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
            
            # Отправляем всем админам
            for admin in admins:
                try:
                    send_message(admin['chat_id'], message)
                except Exception as e:
                    print(f"[ERROR] Failed to notify admin {admin['chat_id']}: {str(e)}")
    
    finally:
        conn.close()


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