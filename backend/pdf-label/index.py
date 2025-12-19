'''
Бизнес: Генерация PDF-термоэтикеток для заявок в форматах 120x75мм и 58x40мм с русским шрифтом
Аргументы: event - dict с httpMethod, body (order_id, label_size)
Возвращает: PDF файл термоэтикетки в base64
'''

import json
import os
from typing import Dict, Any
from reportlab.lib.pagesizes import mm
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm as MM
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
import io
import base64
import psycopg2
from psycopg2.extras import RealDictCursor
import requests as http_client

def get_bot_username() -> str:
    """Получает username бота через Telegram Bot API"""
    try:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            return 'YourBot'
        
        response = http_client.get(f'https://api.telegram.org/bot{bot_token}/getMe', timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('ok') and 'result' in data:
                return data['result'].get('username', 'YourBot')
        return 'YourBot'
    except:
        return 'YourBot'

BOT_USERNAME = get_bot_username()

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method: str = event.get('httpMethod', 'GET')
    
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
    
    if method != 'POST':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }
    
    body_data = json.loads(event.get('body', '{}'))
    order_id = body_data.get('order_id')
    order_type = body_data.get('order_type', 'sender')
    label_size = body_data.get('label_size', '120x75')
    
    if not order_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'order_id is required'}),
            'isBase64Encoded': False
        }
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if order_type == 'sender':
                cur.execute(
                    "SELECT * FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE id = %s",
                    (order_id,)
                )
            else:
                cur.execute(
                    "SELECT * FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE id = %s",
                    (order_id,)
                )
            
            order = cur.fetchone()
            
            if not order:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'Order not found'}),
                    'isBase64Encoded': False
                }
            
            pdf_bytes = generate_label_pdf(order, order_type, label_size)
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'pdf': pdf_base64,
                    'filename': f'label_{order_id}_{label_size}.pdf'
                }),
                'isBase64Encoded': False
            }
    
    finally:
        conn.close()


def download_font():
    font_path = "/tmp/DejaVuSans.ttf"
    
    if not os.path.exists(font_path):
        # Используем надёжный источник - GitHub releases
        font_urls = [
            "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip",
            "https://github.com/google/fonts/raw/main/ofl/roboto/static/Roboto-Regular.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/apache/roboto/static/Roboto-Regular.ttf"
        ]
        
        for font_url in font_urls:
            try:
                print(f"Trying to download font from: {font_url}")
                response = http_client.get(font_url, timeout=10)
                
                if response.status_code == 200:
                    # Если это zip, берём первый TTF файл
                    if font_url.endswith('.zip'):
                        import zipfile
                        import io as io_module
                        with zipfile.ZipFile(io_module.BytesIO(response.content)) as zf:
                            for name in zf.namelist():
                                if 'DejaVuSans.ttf' in name and 'Bold' not in name and 'Oblique' not in name:
                                    with open(font_path, 'wb') as f:
                                        f.write(zf.read(name))
                                    print(f"Font extracted successfully from zip")
                                    return font_path
                    else:
                        with open(font_path, 'wb') as f:
                            f.write(response.content)
                        print(f"Font downloaded successfully from {font_url}")
                        return font_path
            except Exception as e:
                print(f"Failed to download from {font_url}: {e}")
                continue
        
        raise Exception("Failed to download font from all sources")
    
    return font_path


def format_order_text(order: Dict[str, Any], order_type: str) -> str:
    """Форматирует заявку в читаемый текст"""
    if order_type == 'sender':
        lines = []
        lines.append(f"ЗАЯВКА ОТПРАВИТЕЛЯ #{order['id']}")
        if order.get('marketplace'): lines.append(f"Маркетплейс: {order['marketplace']}")
        if order.get('warehouse'): lines.append(f"Склад: {order['warehouse']}")
        if order.get('loading_address'): lines.append(f"Откуда: {order['loading_address']}")
        
        cargo = []
        if order.get('pallet_quantity'): cargo.append(f"{order['pallet_quantity']} паллет")
        if order.get('box_quantity'): cargo.append(f"{order['box_quantity']} коробок")
        if cargo: lines.append(f"Груз: {', '.join(cargo)}")
        
        if order.get('sender_name'): lines.append(f"Контакт: {order['sender_name']}")
        if order.get('phone'): lines.append(f"Телефон: {order['phone']}")
        if order.get('delivery_date'): lines.append(f"Дата поставки: {order['delivery_date']}")
        if order.get('rate'): lines.append(f"Ставка: {order['rate']} руб")
        
        return '\n'.join(lines)
    else:
        lines = []
        lines.append(f"ЗАЯВКА ПЕРЕВОЗЧИКА #{order['id']}")
        if order.get('marketplace'): lines.append(f"Маркетплейс: {order['marketplace']}")
        if order.get('warehouse'): lines.append(f"Склад: {order['warehouse']}")
        
        car = []
        if order.get('car_brand'): car.append(order['car_brand'])
        if order.get('car_model'): car.append(order['car_model'])
        if car: lines.append(f"Автомобиль: {' '.join(car)}")
        
        if order.get('license_plate'): lines.append(f"Номер: {order['license_plate']}")
        
        capacity = []
        if order.get('pallet_capacity'): capacity.append(f"{order['pallet_capacity']} паллет")
        if order.get('box_capacity'): capacity.append(f"{order['box_capacity']} коробок")
        if capacity: lines.append(f"Вместимость: {', '.join(capacity)}")
        
        if order.get('hydroboard'): lines.append(f"Гидроборт: {order['hydroboard']}")
        if order.get('driver_name'): lines.append(f"Водитель: {order['driver_name']}")
        if order.get('phone'): lines.append(f"Телефон: {order['phone']}")
        if order.get('loading_date'): lines.append(f"Дата ПОГРУЗКИ: {order['loading_date']}")
        if order.get('arrival_date'): lines.append(f"Дата прибытия: {order['arrival_date']}")
        
        return '\n'.join(lines)


def generate_label_pdf(order: Dict[str, Any], order_type: str, label_size: str) -> bytes:
    buffer = io.BytesIO()
    
    if label_size == '120x75':
        width, height = 120*MM, 75*MM
        font_size_title = 10
        font_size_normal = 12
        font_size_small = 10
        qr_size = 20*MM
        line_height = 5*MM
    else:
        width, height = 58*MM, 40*MM
        font_size_title = 8
        font_size_normal = 9
        font_size_small = 7
        qr_size = 13*MM
        line_height = 3.5*MM
    
    c = canvas.Canvas(buffer, pagesize=(width, height))
    
    font_path = download_font()
    pdfmetrics.registerFont(TTFont('DejaVu', font_path))
    c.setFont("DejaVu", font_size_title)
    
    y_position = height - 7*MM
    x_margin = 3*MM
    
    # QR-код слева, название бота справа на одном уровне
    try:
        qr_url = f"https://t.me/{BOT_USERNAME}"
        qr_code = QrCodeWidget(qr_url)
        bounds = qr_code.getBounds()
        qr_width = bounds[2] - bounds[0]
        qr_height = bounds[3] - bounds[1]
        qr_drawing = Drawing(qr_size, qr_size, transform=[qr_size/qr_width, 0, 0, qr_size/qr_height, 0, 0])
        qr_drawing.add(qr_code)
        renderPDF.draw(qr_drawing, c, x_margin, y_position - qr_size + 3*MM)
    except:
        pass
    
    # Название бота справа на одном уровне с QR-кодом
    bot_link = f"t.me/{BOT_USERNAME}"
    bot_text_x = x_margin + qr_size + 3*MM
    bot_text_y = y_position - (qr_size / 2)
    c.drawString(bot_text_x, bot_text_y, bot_link)
    
    y_position -= qr_size + 0.5*MM
    
    # Рисуем линию-разделитель
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.line(x_margin, y_position, width - x_margin, y_position)
    
    y_position -= 5*MM
    
    # Выводим текст заявки
    c.setFont("DejaVu", font_size_normal)
    
    order_text = format_order_text(order, order_type)
    
    for line in order_text.split('\n'):
        if y_position < 5*MM:
            break
        
        # Обрезаем слишком длинные строки
        max_chars = 50 if label_size == '120x75' else 28
        if len(line) > max_chars:
            line = line[:max_chars-3] + '...'
        
        c.drawString(x_margin, y_position, line)
        y_position -= line_height
    
    # Убираем нижнюю надпись (больше не выводим t.me/{BOT_USERNAME})
    
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes