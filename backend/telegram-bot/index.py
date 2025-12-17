'''
Бизнес: Telegram бот для пошагового создания заявок отправителей и перевозчиков
Аргументы: event - dict с httpMethod, body (telegram webhook)
Возвращает: HTTP response для Telegram API
'''

import json
import os
from typing import Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from datetime import datetime

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

user_states: Dict[int, Dict[str, Any]] = {}

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method: str = event.get('httpMethod', 'POST')
    
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
        body_data = json.loads(event.get('body', '{}'))
        
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


def process_message(chat_id: int, text: str):
    if text == '/start':
        user_states[chat_id] = {'step': 'choose_service', 'data': {}}
        send_message(
            chat_id,
            "👋 Добро пожаловать!\n\n<b>Выберите услугу:</b>",
            {
                'keyboard': [
                    [{'text': '📦 Отправитель'}],
                    [{'text': '🚚 Перевозчик'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': False
            }
        )
        return
    
    if chat_id not in user_states:
        user_states[chat_id] = {'step': 'choose_service', 'data': {}}
        send_message(
            chat_id,
            "Введите /start чтобы начать",
            {'remove_keyboard': True}
        )
        return
    
    state = user_states[chat_id]
    step = state['step']
    data = state['data']
    
    if step == 'choose_service':
        if '📦' in text or 'отправитель' in text.lower():
            data['type'] = 'sender'
            state['step'] = 'sender_warehouse'
            send_message(chat_id, "📍 <b>Укажите склад назначения</b>\n\nНапример: Wildberries Электросталь", {'remove_keyboard': True})
        elif '🚚' in text or 'перевозчик' in text.lower():
            data['type'] = 'carrier'
            state['step'] = 'carrier_warehouse'
            send_message(
                chat_id,
                "📍 <b>Укажите склад назначения</b>\n\nНапример: Wildberries Электросталь",
                {
                    'keyboard': [
                        [{'text': '📦 Любой склад'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': False
                }
            )
        else:
            send_message(chat_id, "Пожалуйста, выберите услугу из меню")
    
    elif step == 'sender_warehouse':
        data['warehouse'] = text
        state['step'] = 'sender_loading_address'
        send_message(chat_id, "🏠 <b>Укажите адрес погрузки</b>\n\nНапример: г. Москва, ул. Ленина, д. 10")
    
    elif step == 'sender_loading_address':
        data['loading_address'] = text
        state['step'] = 'sender_loading_date'
        send_message(chat_id, "📅 <b>Укажите дату погрузки</b>\n\nФормат: ДД.ММ.ГГГГ\nНапример: 25.12.2025")
    
    elif step == 'sender_loading_date':
        data['loading_date'] = text
        state['step'] = 'sender_loading_time'
        send_message(chat_id, "🕐 <b>Укажите время погрузки</b>\n\nФормат: ЧЧ:ММ\nНапример: 14:30")
    
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
        data['phone'] = text
        state['step'] = 'sender_label_size'
        send_message(
            chat_id,
            "🏷️ <b>Выберите размер термонаклейки</b>",
            {
                'keyboard': [
                    [{'text': '120x75 мм'}],
                    [{'text': '58x40 мм'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'sender_label_size':
        if '120' in text:
            data['label_size'] = '120x75'
        else:
            data['label_size'] = '58x40'
        
        save_sender_order(chat_id, data)
    
    elif step == 'carrier_warehouse':
        if 'любой' in text.lower():
            data['warehouse'] = 'Любой склад'
        else:
            data['warehouse'] = text
        state['step'] = 'carrier_car_brand'
        send_message(chat_id, "🚗 <b>Укажите марку автомобиля</b>\n\nНапример: Mercedes")
    
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
        data['phone'] = text
        save_carrier_order(chat_id, data)


def save_sender_order(chat_id: int, data: Dict[str, Any]):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO sender_orders (
                    loading_address, warehouse, loading_date, loading_time,
                    pallet_quantity, box_quantity, sender_name, phone, label_size
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data['loading_address'],
                data['warehouse'],
                data['loading_date'],
                data['loading_time'],
                data.get('pallet_quantity', 0),
                data.get('box_quantity', 0),
                data['sender_name'],
                data['phone'],
                data.get('label_size', '120x75')
            ))
            
            order_id = cur.fetchone()['id']
            conn.commit()
            
            send_message(
                chat_id,
                f"✅ <b>Заявка отправителя создана!</b>\n\n"
                f"📋 ID заявки: {order_id}\n"
                f"📍 Склад: {data['warehouse']}\n"
                f"🏠 Адрес погрузки: {data['loading_address']}\n"
                f"📅 Дата: {data['loading_date']} {data['loading_time']}\n"
                f"📦 Груз: {data.get('pallet_quantity', 0)} паллет, {data.get('box_quantity', 0)} коробок\n\n"
                f"Для новой заявки введите /start",
                {'remove_keyboard': True}
            )
            
            user_states[chat_id] = {'step': 'choose_service', 'data': {}}
    
    finally:
        conn.close()


def save_carrier_order(chat_id: int, data: Dict[str, Any]):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO carrier_orders (
                    car_brand, car_model, license_plate, pallet_capacity,
                    box_capacity, warehouse, driver_name, phone
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data['car_brand'],
                data['car_model'],
                data['license_plate'],
                data.get('pallet_capacity', 0),
                data.get('box_capacity', 0),
                data.get('warehouse', ''),
                data['driver_name'],
                data['phone']
            ))
            
            order_id = cur.fetchone()['id']
            conn.commit()
            
            send_message(
                chat_id,
                f"✅ <b>Заявка перевозчика создана!</b>\n\n"
                f"📋 ID заявки: {order_id}\n"
                f"🚗 Автомобиль: {data['car_brand']} {data['car_model']}\n"
                f"🔢 Номер: {data['license_plate']}\n"
                f"📦 Вместимость: {data.get('pallet_capacity', 0)} паллет, {data.get('box_capacity', 0)} коробок\n\n"
                f"Для новой заявки введите /start",
                {'remove_keyboard': True}
            )
            
            user_states[chat_id] = {'step': 'choose_service', 'data': {}}
    
    finally:
        conn.close()