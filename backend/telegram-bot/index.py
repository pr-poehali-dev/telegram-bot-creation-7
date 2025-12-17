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
SESSION_TIMEOUT = 6 * 60 * 60

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
        
        if 'callback_query' in body_data:
            callback = body_data['callback_query']
            chat_id = callback['message']['chat']['id']
            callback_data = callback['data']
            message_id = callback['message']['message_id']
            
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
            'loading_date': 'дату погрузки',
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
            'driver_name': 'ФИО водителя'
        }
        
        send_message(
            chat_id,
            f"✏️ Введите новое значение для <b>{field_names.get(field, field)}</b>:"
        )
    
    elif callback_data == 'confirm_create':
        if data.get('type') == 'sender':
            save_sender_order(chat_id, data)
        else:
            save_carrier_order(chat_id, data)
    
    elif callback_data.startswith('admin_'):
        if str(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "❌ У вас нет прав администратора")
            return
        
        if callback_data == 'admin_stats':
            show_admin_stats(chat_id)
        elif callback_data == 'admin_delete':
            state['admin_action'] = 'delete'
            send_message(chat_id, "📝 Введите ID заявки для удаления (например: 123)")
        elif callback_data == 'admin_block':
            state['admin_action'] = 'block'
            send_message(chat_id, "📝 Введите Chat ID пользователя для блокировки")
        elif callback_data == 'admin_unblock':
            state['admin_action'] = 'unblock'
            send_message(chat_id, "📝 Введите Chat ID пользователя для разблокировки")
        elif callback_data == 'admin_cleanup':
            cleanup_old_orders(chat_id)
    
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
    if text == '/admin':
        if str(chat_id) != ADMIN_CHAT_ID:
            send_message(chat_id, "❌ У вас нет прав администратора")
            return
        
        send_message(
            chat_id,
            "🔧 <b>Админ-панель</b>\n\n" +
            "Выберите действие:",
            {
                'inline_keyboard': [
                    [{'text': '📊 Статистика', 'callback_data': 'admin_stats'}],
                    [{'text': '🗑️ Удалить заявку', 'callback_data': 'admin_delete'}],
                    [{'text': '🚫 Заблокировать пользователя', 'callback_data': 'admin_block'}],
                    [{'text': '✅ Разблокировать пользователя', 'callback_data': 'admin_unblock'}],
                    [{'text': '🧹 Очистить старые заявки', 'callback_data': 'admin_cleanup'}]
                ]
            }
        )
        return
    
    if text == '/start':
        user_states[chat_id] = {'step': 'choose_service', 'data': {}, 'last_activity': time.time()}
        send_message(
            chat_id,
            "👋 Добро пожаловать!\n\n<b>Выберите услугу:</b>",
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
    
    if state.get('editing_field'):
        field = state['editing_field']
        
        if field in ['pallet_quantity', 'box_quantity', 'pallet_capacity', 'box_capacity']:
            data[field] = int(text) if text.isdigit() else 0
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
        data['phone'] = text
        state['step'] = 'sender_label_size'
        send_message(
            chat_id,
            "🏷️ <b>Выберите термонаклейку с инфо для водителя</b>",
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
        
        send_message(chat_id, "⏳ Генерирую термонаклейку...")
        generate_and_send_label(chat_id, data)
    
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
        data['phone'] = text
        state['step'] = 'carrier_label_size'
        send_message(
            chat_id,
            "🏷️ <b>Выберите термонаклейку с инфо для водителя</b>",
            {
                'keyboard': [
                    [{'text': '120x75 мм'}],
                    [{'text': '58x40 мм'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'carrier_label_size':
        if '120' in text:
            data['label_size'] = '120x75'
        else:
            data['label_size'] = '58x40'
        
        send_message(chat_id, "⏳ Генерирую термонаклейку...")
        generate_and_send_label(chat_id, data)


def generate_and_send_label(chat_id: int, data: Dict[str, Any]):
    try:
        temp_order_data = {
            'id': 'preview',
            'marketplace': data.get('marketplace', ''),
            'warehouse': data.get('warehouse', ''),
            'phone': data.get('phone', '')
        }
        
        if data['type'] == 'sender':
            temp_order_data.update({
                'loading_address': data.get('loading_address', ''),
                'loading_date': data.get('loading_date', ''),
                'loading_time': data.get('loading_time', ''),
                'pallet_quantity': data.get('pallet_quantity', 0),
                'box_quantity': data.get('box_quantity', 0),
                'sender_name': data.get('sender_name', '')
            })
        else:
            temp_order_data.update({
                'car_brand': data.get('car_brand', ''),
                'car_model': data.get('car_model', ''),
                'license_plate': data.get('license_plate', ''),
                'pallet_capacity': data.get('pallet_capacity', 0),
                'box_capacity': data.get('box_capacity', 0),
                'driver_name': data.get('driver_name', '')
            })
        
        import base64
        from reportlab.lib.pagesizes import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm as MM
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
        import io
        
        buffer = io.BytesIO()
        
        label_size = data.get('label_size', '120x75')
        if label_size == '120x75':
            width, height = 120*MM, 75*MM
            font_size_title = 12
            font_size_normal = 9
            font_size_small = 7
            qr_size = 15*MM
        else:
            width, height = 58*MM, 40*MM
            font_size_title = 8
            font_size_normal = 6
            font_size_small = 5
            qr_size = 10*MM
        
        c = canvas.Canvas(buffer, pagesize=(width, height))
        
        bot_username = os.environ.get('TELEGRAM_BOT_USERNAME', 'your_bot')
        qr_url = f"https://t.me/{bot_username}"
        
        qr_code = QrCodeWidget(qr_url)
        qr_drawing = Drawing(qr_size, qr_size, transform=[qr_size/qr_code.width, 0, 0, qr_size/qr_code.width, 0, 0])
        qr_drawing.add(qr_code)
        
        qr_x = width - qr_size - 5*MM
        qr_y = height - qr_size - 5*MM
        renderPDF.draw(qr_drawing, c, qr_x, qr_y)
        
        y_position = height - 10*MM
        x_margin = 5*MM
        
        c.setFont("Helvetica-Bold", font_size_title)
        c.drawString(x_margin, y_position, "CARGO EXPRESS")
        
        y_position -= 6*MM
        c.setFont("Helvetica", font_size_small)
        title = "Otpravitel" if data['type'] == 'sender' else "Perevozchik"
        c.drawString(x_margin, y_position, title)
        
        y_position -= 6*MM
        c.setFont("Helvetica", font_size_normal)
        
        marketplace = temp_order_data.get('marketplace', '')
        c.drawString(x_margin, y_position, f"MP: {marketplace}")
        y_position -= 5*MM
        
        warehouse = temp_order_data.get('warehouse', '')
        c.drawString(x_margin, y_position, f"Sklad: {warehouse}")
        y_position -= 5*MM
        
        if data['type'] == 'sender':
            if temp_order_data.get('loading_address'):
                addr = temp_order_data['loading_address'][:25]
                c.drawString(x_margin, y_position, f"Adres: {addr}")
                y_position -= 4*MM
            
            date_str = temp_order_data.get('loading_date', '')
            time_str = temp_order_data.get('loading_time', '')
            c.drawString(x_margin, y_position, f"Data: {date_str} {time_str}")
            y_position -= 4*MM
            
            pallet = temp_order_data.get('pallet_quantity', 0)
            boxes = temp_order_data.get('box_quantity', 0)
            c.drawString(x_margin, y_position, f"Gruz: {pallet} pal, {boxes} kor")
            y_position -= 4*MM
            
            sender = temp_order_data.get('sender_name', '')[:20]
            c.drawString(x_margin, y_position, f"FIO: {sender}")
        else:
            car_brand = temp_order_data.get('car_brand', '')
            car_model = temp_order_data.get('car_model', '')
            c.drawString(x_margin, y_position, f"Avto: {car_brand} {car_model}")
            y_position -= 4*MM
            
            plate = temp_order_data.get('license_plate', '')
            c.drawString(x_margin, y_position, f"Nomer: {plate}")
            y_position -= 4*MM
            
            pallet = temp_order_data.get('pallet_capacity', 0)
            boxes = temp_order_data.get('box_capacity', 0)
            c.drawString(x_margin, y_position, f"Vmest: {pallet} pal, {boxes} kor")
            y_position -= 4*MM
            
            driver = temp_order_data.get('driver_name', '')[:20]
            c.drawString(x_margin, y_position, f"Voditel: {driver}")
        
        y_position -= 4*MM
        phone = temp_order_data.get('phone', '')
        c.drawString(x_margin, y_position, f"Tel: {phone}")
        
        c.save()
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        filename = f"label_{data['type']}_{data.get('label_size', '120x75')}.pdf"
        send_document(chat_id, pdf_bytes, filename, "✅ Термонаклейка готова!")
        
        user_states[chat_id]['step'] = 'show_preview'
        show_preview(chat_id, data)
    
    except Exception as e:
        send_message(chat_id, f"❌ Ошибка генерации термонаклейки: {str(e)}")


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
            f"🏷️ Термонаклейка: {data.get('label_size', '-')}"
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
                    {'text': '✏️ Телефон', 'callback_data': 'edit_phone'}
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
            f"👤 Водитель: {data.get('driver_name', '-')}\n"
            f"📱 Телефон: {data.get('phone', '-')}\n"
            f"🏷️ Термонаклейка: {data.get('label_size', '-')}"
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
                    {'text': '✏️ Водитель', 'callback_data': 'edit_driver_name'}
                ],
                [
                    {'text': '✏️ Телефон', 'callback_data': 'edit_phone'}
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
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.sender_orders
                (loading_address, warehouse, loading_date, loading_time, pallet_quantity, box_quantity, sender_name, phone, label_size, marketplace)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    data.get('marketplace')
                )
            )
            
            order_id = cur.fetchone()['id']
            conn.commit()
            
            send_message(
                chat_id,
                f"✅ <b>Заявка #{order_id} создана!</b>\n\nПеревозчики получили уведомление о вашем грузе.",
                {'remove_keyboard': True}
            )
            
            notify_about_new_order(order_id, 'sender', data)
            send_notifications_to_subscribers(order_id, 'sender', data)
            ask_notification_settings(chat_id, 'sender', data)
    
    finally:
        conn.close()


def save_carrier_order(chat_id: int, data: Dict[str, Any]):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO t_p52349012_telegram_bot_creatio.carrier_orders
                (warehouse, car_brand, car_model, license_plate, pallet_capacity, box_capacity, driver_name, phone, label_size, marketplace)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    data.get('label_size'),
                    data.get('marketplace')
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
                "SELECT id, marketplace, warehouse FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE phone LIKE %s ORDER BY id DESC LIMIT 10",
                (f'%{chat_id}%',)
            )
            carrier_orders = cur.fetchall()
            
            if not sender_orders and not carrier_orders:
                send_message(chat_id, "У вас пока нет заявок")
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
                    message_parts.append(
                        f"#{order['id']} - {order.get('marketplace', '-')} → {order.get('warehouse', '-')}\n"
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
            f"📱 Телефон: {data.get('phone')}"
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
            
            cur.execute(
                """
                SELECT DISTINCT chat_id FROM t_p52349012_telegram_bot_creatio.user_subscriptions
                WHERE user_type = %s
                AND (subscription_type = 'all' OR (subscription_type = 'warehouse' AND warehouse_filter = %s))
                """,
                (target_user_type, warehouse)
            )
            
            subscribers = cur.fetchall()
            
            if order_type == 'sender':
                message = (
                    f"🆕 <b>Новая заявка отправителя #{order_id}</b>\n\n"
                    f"🏪 Маркетплейс: {data.get('marketplace', '-')}\n"
                    f"📍 Склад: {data.get('warehouse')}\n"
                    f"📅 Дата: {data.get('loading_date')} {data.get('loading_time')}\n"
                    f"📦 Груз: {data.get('pallet_quantity', 0)} паллет, {data.get('box_quantity', 0)} коробок\n"
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