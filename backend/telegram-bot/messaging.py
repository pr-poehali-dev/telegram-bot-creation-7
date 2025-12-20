"""
Модуль для отправки сообщений в Telegram
Все функции взаимодействия с Telegram Bot API
"""

import json
import os
from typing import Dict, Optional
import requests
from datetime import datetime

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
ADMIN_CHAT_ID = os.environ.get('TELEGRAM_ADMIN_CHAT_ID', '')
PDF_FUNCTION_URL = 'https://functions.poehali.dev/a68807d2-57ae-4e99-b9e2-44b1dcfcc5b6'

def send_message(chat_id: int, text: str, reply_markup: Optional[Dict] = None):
    url = f"{BASE_URL}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"[ERROR] send_message failed: {str(e)}")
        return None

def edit_message(chat_id: int, message_id: int, text: str, reply_markup: Optional[Dict] = None):
    url = f"{BASE_URL}/editMessageText"
    data = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"[ERROR] edit_message failed: {str(e)}")
        return None

def delete_message(chat_id: int, message_id: int):
    url = f"{BASE_URL}/deleteMessage"
    data = {
        'chat_id': chat_id,
        'message_id': message_id
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"[ERROR] delete_message failed: {str(e)}")
        return None

def answer_callback_query(callback_query_id: str, text: Optional[str] = None, show_alert: bool = False):
    url = f"{BASE_URL}/answerCallbackQuery"
    data = {
        'callback_query_id': callback_query_id,
        'show_alert': show_alert
    }
    if text:
        data['text'] = text
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"[ERROR] answer_callback_query failed: {str(e)}")
        return None

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

def send_document(chat_id: int, document_bytes: bytes, filename: str, caption: str = ''):
    url = f"{BASE_URL}/sendDocument"
    files = {'document': (filename, document_bytes, 'application/pdf')}
    data = {
        'chat_id': chat_id,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    try:
        requests.post(url, data=data, files=files, timeout=10)
    except Exception as e:
        print(f"[ERROR] send_document failed: {str(e)}")

def send_label_to_user(chat_id: int, order_id: int, order_type: str, label_size: str = '58x40'):
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
                send_message(chat_id, "❌ Ошибка при генерации PDF")
        else:
            send_message(chat_id, "❌ Ошибка при генерации термоэтикетки")
            
    except Exception as e:
        send_message(chat_id, f"❌ Ошибка при генерации термоэтикетки: {str(e)}")

def notify_carriers_about_new_order(order_id: int, sender_data: dict):
    from database import normalize_warehouse
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT chat_id
                FROM t_p52349012_telegram_bot_creatio.carrier_orders
                WHERE chat_id != %s
                ORDER BY created_at DESC
                LIMIT 50
            """, (sender_data['chat_id'],))
            
            carriers = cur.fetchall()
        
        conn.close()
        
        for carrier in carriers:
            message = f"""
🆕 <b>Новая заявка отправителя #{order_id}</b>

📦 <b>Маркетплейс:</b> {sender_data.get('marketplace', 'Не указан')}
📍 <b>Откуда:</b> {sender_data.get('from_warehouse', 'Не указан')}
📍 <b>Куда:</b> {sender_data.get('to_warehouse', 'Не указан')}
📦 <b>Паллеты:</b> {sender_data.get('pallets_count', 'Не указано')}
📦 <b>Тип груза:</b> {sender_data.get('cargo_type', 'Не указан')}
📅 <b>Дата отправки:</b> {sender_data.get('shipping_date', 'Не указана')}
"""
            if sender_data.get('additional_info'):
                message += f"\n💬 <b>Комментарий:</b> {sender_data.get('additional_info')}"
            
            send_message(carrier['chat_id'], message)
            
    except Exception as e:
        print(f"[ERROR] notify_carriers failed: {str(e)}")

def notify_senders_about_new_carrier(order_id: int, carrier_data: dict):
    from database import normalize_warehouse
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT chat_id
                FROM t_p52349012_telegram_bot_creatio.sender_orders
                WHERE chat_id != %s
                ORDER BY created_at DESC
                LIMIT 50
            """, (carrier_data['chat_id'],))
            
            senders = cur.fetchall()
        
        conn.close()
        
        for sender in senders:
            message = f"""
🚚 <b>Новый перевозчик #{order_id}</b>

📍 <b>Откуда:</b> {carrier_data.get('from_warehouse', 'Не указан')}
📍 <b>Куда:</b> {carrier_data.get('to_warehouse', 'Не указан')}
🚗 <b>Тип авто:</b> {carrier_data.get('truck_type', 'Не указан')}
💵 <b>Цена:</b> {carrier_data.get('price', 'Не указана')}
"""
            if carrier_data.get('additional_info'):
                message += f"\n💬 <b>Комментарий:</b> {carrier_data.get('additional_info')}"
            
            send_message(sender['chat_id'], message)
            
    except Exception as e:
        print(f"[ERROR] notify_senders failed: {str(e)}")