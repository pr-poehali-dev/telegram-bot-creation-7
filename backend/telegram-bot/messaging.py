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

def send_label_to_user(chat_id: int, order_id: int, order_type: str):
    from database import get_order_by_id
    
    try:
        order = get_order_by_id(order_id, order_type)
        if not order:
            send_message(chat_id, "Заявка не найдена.")
            return
        
        pdf_data = {
            'order_id': order_id,
            'order_type': order_type,
            'order_data': order
        }
        
        response = requests.post(PDF_FUNCTION_URL, json=pdf_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            pdf_url = result.get('pdf_url')
            
            if pdf_url:
                send_message(chat_id, f"📄 Ваша этикетка готова!\n\n{pdf_url}")
            else:
                send_message(chat_id, "Ошибка при генерации этикетки.")
        else:
            send_message(chat_id, "Не удалось создать этикетку. Попробуйте позже.")
    except Exception as e:
        send_message(chat_id, "Произошла ошибка при создании этикетки.")
