import json
import os
from typing import Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

def get_db_connection():
    dsn = os.environ.get('DATABASE_URL')
    return psycopg2.connect(dsn)

def send_telegram_notification(order_type: str, order_id: int, data: Dict[str, Any]):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_ADMIN_CHAT_ID', '')
    
    if not bot_token or not chat_id:
        return
    
    if order_type == 'sender':
        message = (
            f"📦 <b>Новая заявка отправителя #{order_id}</b>\n\n"
            f"📍 Склад: {data.get('warehouse', 'Не указан')}\n"
            f"🏠 Адрес погрузки: {data.get('loading_address', 'Не указан')}\n"
            f"📅 Дата: {data.get('loading_date', '')} {data.get('loading_time', '')}\n"
            f"📦 Груз: {data.get('pallet_quantity', 0)} паллет, {data.get('box_quantity', 0)} коробок\n"
            f"👤 Отправитель: {data.get('sender_name', '')}\n"
            f"📱 Телефон: {data.get('phone', '')}"
        )
    else:
        message = (
            f"🚚 <b>Новая заявка перевозчика #{order_id}</b>\n\n"
            f"🚗 Автомобиль: {data.get('car_brand', '')} {data.get('car_model', '')}\n"
            f"🔢 Номер: {data.get('license_plate', '')}\n"
            f"📦 Вместимость: {data.get('pallet_capacity', 0)} паллет, {data.get('box_capacity', 0)} коробок\n"
            f"📍 Склад: {data.get('warehouse', 'Не указан')}\n"
            f"👤 Водитель: {data.get('driver_name', '')}\n"
            f"📱 Телефон: {data.get('phone', '')}"
        )
    
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
        )
    except:
        pass

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method: str = event.get('httpMethod', 'GET')
    
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': '',
            'isBase64Encoded': False
        }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        if method == 'GET':
            sender_query = """
                SELECT 'sender' as type, id, loading_address, warehouse, 
                       loading_date::text, loading_time::text,
                       pallet_quantity, box_quantity, sender_name, phone, 
                       photo_url, label_size, created_at
                FROM sender_orders
                ORDER BY created_at DESC
            """
            
            carrier_query = """
                SELECT 'carrier' as type, id, car_brand, car_model,
                       license_plate, pallet_capacity, box_capacity,
                       warehouse, driver_name, phone, photo_url, 
                       license_number, created_at
                FROM carrier_orders
                ORDER BY created_at DESC
            """
            
            cursor.execute(sender_query)
            sender_orders = cursor.fetchall()
            
            cursor.execute(carrier_query)
            carrier_orders = cursor.fetchall()
            
            result = []
            
            for order in sender_orders:
                result.append({
                    'type': 'sender',
                    'id': order['id'],
                    'loadingAddress': order['loading_address'],
                    'warehouse': order['warehouse'],
                    'loadingDate': order['loading_date'],
                    'loadingTime': order['loading_time'],
                    'palletQuantity': order['pallet_quantity'],
                    'boxQuantity': order['box_quantity'],
                    'senderName': order['sender_name'],
                    'phone': order['phone'],
                    'photo': order['photo_url'],
                    'labelSize': order['label_size'],
                    'createdAt': order['created_at'].isoformat() if order['created_at'] else None
                })
            
            for order in carrier_orders:
                result.append({
                    'type': 'carrier',
                    'id': order['id'],
                    'carBrand': order['car_brand'],
                    'carModel': order['car_model'],
                    'licensePlate': order['license_plate'],
                    'palletCapacity': order['pallet_capacity'],
                    'boxCapacity': order['box_capacity'],
                    'warehouse': order['warehouse'],
                    'driverName': order['driver_name'],
                    'phone': order['phone'],
                    'photo': order['photo_url'],
                    'licenseNumber': order['license_number'],
                    'createdAt': order['created_at'].isoformat() if order['created_at'] else None
                })
            
            cursor.close()
            conn.close()
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'orders': result}),
                'isBase64Encoded': False
            }
        
        elif method == 'POST':
            body = json.loads(event.get('body', '{}'))
            order_type = body.get('type')
            
            if order_type == 'sender':
                cursor.execute("""
                    INSERT INTO sender_orders (
                        loading_address, warehouse, loading_date, loading_time,
                        pallet_quantity, box_quantity, sender_name, phone, label_size,
                        cargo_type, cargo_quantity
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at
                """, (
                    body.get('loadingAddress') or body.get('pickupAddress'),
                    body.get('warehouse'),
                    body.get('loadingDate') or body.get('deliveryDate'),
                    body.get('loadingTime'),
                    body.get('palletQuantity', 0),
                    body.get('boxQuantity', 0),
                    body.get('senderName'),
                    body.get('phone'),
                    body.get('labelSize', '120x75'),
                    'pallet',
                    0
                ))
                
                result = cursor.fetchone()
                conn.commit()
                
                send_telegram_notification('sender', result['id'], body)
                
                cursor.close()
                conn.close()
                
                return {
                    'statusCode': 201,
                    'headers': headers,
                    'body': json.dumps({
                        'id': result['id'],
                        'created_at': result['created_at'].isoformat()
                    }),
                    'isBase64Encoded': False
                }
            
            elif order_type == 'carrier':
                cursor.execute("""
                    INSERT INTO carrier_orders (
                        car_brand, car_model, license_plate, pallet_capacity,
                        box_capacity, warehouse, driver_name, phone,
                        capacity_type, capacity_quantity
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at
                """, (
                    body.get('carBrand'),
                    body.get('carModel'),
                    body.get('licensePlate'),
                    body.get('palletCapacity', 0),
                    body.get('boxCapacity', 0),
                    body.get('warehouse', ''),
                    body.get('driverName'),
                    body.get('phone'),
                    'pallet',
                    0
                ))
                
                result = cursor.fetchone()
                conn.commit()
                
                send_telegram_notification('carrier', result['id'], body)
                
                cursor.close()
                conn.close()
                
                return {
                    'statusCode': 201,
                    'headers': headers,
                    'body': json.dumps({
                        'id': result['id'],
                        'created_at': result['created_at'].isoformat()
                    }),
                    'isBase64Encoded': False
                }
            
            else:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': 'Invalid order type'}),
                    'isBase64Encoded': False
                }
        
        else:
            return {
                'statusCode': 405,
                'headers': headers,
                'body': json.dumps({'error': 'Method not allowed'}),
                'isBase64Encoded': False
            }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)}),
            'isBase64Encoded': False
        }