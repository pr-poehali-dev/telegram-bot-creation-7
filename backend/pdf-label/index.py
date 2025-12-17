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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
import io
import base64
import psycopg2
from psycopg2.extras import RealDictCursor

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


def generate_label_pdf(order: Dict[str, Any], order_type: str, label_size: str) -> bytes:
    buffer = io.BytesIO()
    
    if label_size == '120x75':
        width, height = 120*MM, 75*MM
        font_size_title = 14
        font_size_normal = 10
        font_size_small = 8
    else:
        width, height = 58*MM, 40*MM
        font_size_title = 10
        font_size_normal = 7
        font_size_small = 6
    
    c = canvas.Canvas(buffer, pagesize=(width, height))
    
    y_position = height - 10*MM
    x_margin = 5*MM
    
    c.setFont("Helvetica-Bold", font_size_title)
    if order_type == 'sender':
        c.drawString(x_margin, y_position, "ЗАЯВКА ОТПРАВИТЕЛЯ")
    else:
        c.drawString(x_margin, y_position, "ЗАЯВКА ПЕРЕВОЗЧИКА")
    
    y_position -= 8*MM
    c.setFont("Helvetica", font_size_normal)
    
    if order_type == 'sender':
        c.drawString(x_margin, y_position, f"ID: {order['id']}")
        y_position -= 6*MM
        
        if order.get('loading_address'):
            c.drawString(x_margin, y_position, f"Адрес погрузки:")
            y_position -= 5*MM
            c.setFont("Helvetica-Bold", font_size_small)
            c.drawString(x_margin + 2*MM, y_position, str(order['loading_address']))
            y_position -= 6*MM
        
        c.setFont("Helvetica", font_size_normal)
        if order.get('warehouse'):
            c.drawString(x_margin, y_position, f"Склад: {order['warehouse']}")
            y_position -= 5*MM
        
        if order.get('loading_date'):
            date_str = str(order['loading_date'])
            time_str = str(order.get('loading_time', ''))
            c.drawString(x_margin, y_position, f"Дата: {date_str} {time_str}")
            y_position -= 5*MM
        
        pallet_qty = order.get('pallet_quantity', 0)
        box_qty = order.get('box_quantity', 0)
        if pallet_qty or box_qty:
            cargo_text = []
            if pallet_qty: cargo_text.append(f"{pallet_qty} паллет")
            if box_qty: cargo_text.append(f"{box_qty} коробок")
            c.drawString(x_margin, y_position, "Груз: " + ", ".join(cargo_text))
            y_position -= 5*MM
        
        if order.get('sender_name'):
            c.drawString(x_margin, y_position, f"Отправитель: {order['sender_name']}")
            y_position -= 5*MM
        
        if order.get('phone'):
            c.drawString(x_margin, y_position, f"Телефон: {order['phone']}")
    
    else:
        c.drawString(x_margin, y_position, f"ID: {order['id']}")
        y_position -= 6*MM
        
        if order.get('car_brand') or order.get('car_model'):
            car_info = f"{order.get('car_brand', '')} {order.get('car_model', '')}".strip()
            c.drawString(x_margin, y_position, f"Авто: {car_info}")
            y_position -= 5*MM
        
        if order.get('license_plate'):
            c.drawString(x_margin, y_position, f"Номер: {order['license_plate']}")
            y_position -= 5*MM
        
        pallet_cap = order.get('pallet_capacity', 0)
        box_cap = order.get('box_capacity', 0)
        if pallet_cap or box_cap:
            capacity_text = []
            if pallet_cap: capacity_text.append(f"{pallet_cap} паллет")
            if box_cap: capacity_text.append(f"{box_cap} коробок")
            c.drawString(x_margin, y_position, "Вместимость: " + ", ".join(capacity_text))
            y_position -= 5*MM
        
        if order.get('driver_name'):
            c.drawString(x_margin, y_position, f"Водитель: {order['driver_name']}")
            y_position -= 5*MM
        
        if order.get('phone'):
            c.drawString(x_margin, y_position, f"Телефон: {order['phone']}")
    
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes
