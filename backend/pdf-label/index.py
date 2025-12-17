'''
Бизнес: Генерация PDF-термонаклеек для заявок в форматах 120x75мм и 58x40мм
Аргументы: event - dict с httpMethod, body (order_id, label_size)
Возвращает: PDF файл термонаклейки в base64
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
import io
import base64
import psycopg2
from psycopg2.extras import RealDictCursor

BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME', 'CargoExpressBot')

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
                    "SELECT * FROM sender_orders WHERE id = %s",
                    (order_id,)
                )
            else:
                cur.execute(
                    "SELECT * FROM carrier_orders WHERE id = %s",
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


def transliterate(text: str) -> str:
    trans_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }
    result = []
    for char in text:
        result.append(trans_map.get(char, char))
    return ''.join(result)


def generate_label_pdf(order: Dict[str, Any], order_type: str, label_size: str) -> bytes:
    buffer = io.BytesIO()
    
    if label_size == '120x75':
        width, height = 120*MM, 75*MM
        font_size_title = 12
        font_size_normal = 9
        font_size_small = 7
        qr_size = 15*MM
    else:
        width, height = 58*MM, 40*MM
        font_size_title = 9
        font_size_normal = 6
        font_size_small = 5
        qr_size = 10*MM
    
    c = canvas.Canvas(buffer, pagesize=(width, height))
    
    y_position = height - 8*MM
    x_margin = 3*MM
    
    c.setFont("Helvetica-Bold", font_size_title)
    c.drawString(x_margin, y_position, "CARGO EXPRESS")
    
    qr_url = f"https://t.me/{BOT_USERNAME}?start=order_{order['id']}"
    qr_code = QrCodeWidget(qr_url)
    bounds = qr_code.getBounds()
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]
    qr_drawing = Drawing(qr_size, qr_size, transform=[qr_size/qr_width, 0, 0, qr_size/qr_height, 0, 0])
    qr_drawing.add(qr_code)
    renderPDF.draw(qr_drawing, c, width - qr_size - 3*MM, height - qr_size - 8*MM)
    
    y_position -= 7*MM
    c.setFont("Helvetica", font_size_normal)
    
    if order_type == 'sender':
        c.drawString(x_margin, y_position, f"SENDER ORDER #{order['id']}")
        y_position -= 5*MM
        
        if order.get('marketplace'):
            mp = transliterate(str(order['marketplace']))
            c.drawString(x_margin, y_position, f"Marketplace: {mp}")
            y_position -= 4*MM
        
        if order.get('warehouse'):
            wh = transliterate(str(order['warehouse']))
            c.drawString(x_margin, y_position, f"Warehouse: {wh}")
            y_position -= 4*MM
        
        if order.get('loading_address'):
            addr = transliterate(str(order['loading_address']))
            c.setFont("Helvetica", font_size_small)
            c.drawString(x_margin, y_position, f"From: {addr[:45]}")
            y_position -= 4*MM
        
        c.setFont("Helvetica", font_size_normal)
        if order.get('loading_date'):
            date_str = str(order['loading_date'])
            time_str = str(order.get('loading_time', ''))
            c.drawString(x_margin, y_position, f"Date: {date_str} {time_str}")
            y_position -= 4*MM
        
        pallet_qty = order.get('pallet_quantity', 0)
        box_qty = order.get('box_quantity', 0)
        if pallet_qty or box_qty:
            cargo_parts = []
            if pallet_qty: cargo_parts.append(f"{pallet_qty} pallets")
            if box_qty: cargo_parts.append(f"{box_qty} boxes")
            c.drawString(x_margin, y_position, "Cargo: " + ", ".join(cargo_parts))
            y_position -= 4*MM
        
        if order.get('sender_name'):
            name = transliterate(str(order['sender_name']))
            c.drawString(x_margin, y_position, f"Contact: {name}")
            y_position -= 4*MM
        
        if order.get('phone'):
            c.drawString(x_margin, y_position, f"Phone: {order['phone']}")
    
    else:
        c.drawString(x_margin, y_position, f"CARRIER ORDER #{order['id']}")
        y_position -= 5*MM
        
        if order.get('car_brand') or order.get('car_model'):
            brand = transliterate(str(order.get('car_brand', '')))
            model = transliterate(str(order.get('car_model', '')))
            car_info = f"{brand} {model}".strip()
            c.drawString(x_margin, y_position, f"Vehicle: {car_info}")
            y_position -= 4*MM
        
        if order.get('license_plate'):
            plate = transliterate(str(order['license_plate']))
            c.drawString(x_margin, y_position, f"Plate: {plate}")
            y_position -= 4*MM
        
        pallet_cap = order.get('pallet_capacity', 0)
        box_cap = order.get('box_capacity', 0)
        if pallet_cap or box_cap:
            cap_parts = []
            if pallet_cap: cap_parts.append(f"{pallet_cap} pallets")
            if box_cap: cap_parts.append(f"{box_cap} boxes")
            c.drawString(x_margin, y_position, "Capacity: " + ", ".join(cap_parts))
            y_position -= 4*MM
        
        if order.get('driver_name'):
            driver = transliterate(str(order['driver_name']))
            c.drawString(x_margin, y_position, f"Driver: {driver}")
            y_position -= 4*MM
        
        if order.get('phone'):
            c.drawString(x_margin, y_position, f"Phone: {order['phone']}")
    
    c.setFont("Helvetica", font_size_small)
    c.drawString(x_margin, 3*MM, f"t.me/{BOT_USERNAME}")
    
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes