import json
import os
from typing import Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """Создание подключения к базе данных"""
    dsn = os.environ.get('DATABASE_URL')
    return psycopg2.connect(dsn)

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    API для работы с заявками грузоперевозок
    GET / - получить все заявки
    POST /sender - создать заявку отправителя
    POST /carrier - создать заявку перевозчика
    """
    method: str = event.get('httpMethod', 'GET')
    path: str = event.get('path', '/')
    
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
                SELECT 'sender' as type, id, pickup_address as field1, pickup_comments as field2, 
                       warehouse as field3, delivery_date::text as field4, cargo_type as field5, 
                       cargo_quantity::text as field6, sender_name as name, phone, 
                       photo_url as field7, label_size as field8, created_at
                FROM sender_orders
            """
            
            carrier_query = """
                SELECT 'carrier' as type, id, car_brand as field1, car_model as field2,
                       license_plate as field3, NULL as field4, capacity_type as field5,
                       capacity_quantity::text as field6, warehouse as field8, driver_name as name,
                       phone, photo_url as field7, license_number as field9, created_at
                FROM carrier_orders
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
                    'pickupAddress': order['field1'],
                    'pickupComments': order['field2'],
                    'warehouse': order['field3'],
                    'deliveryDate': order['field4'],
                    'cargoType': order['field5'],
                    'cargoQuantity': order['field6'],
                    'senderName': order['name'],
                    'phone': order['phone'],
                    'photo': order['field7'],
                    'labelSize': order['field8'],
                    'createdAt': order['created_at'].isoformat() if order['created_at'] else None
                })
            
            for order in carrier_orders:
                result.append({
                    'type': 'carrier',
                    'id': order['id'],
                    'carBrand': order['field1'],
                    'carModel': order['field2'],
                    'licensePlate': order['field3'],
                    'capacityType': order['field5'],
                    'capacityQuantity': order['field6'],
                    'warehouse': order['field8'],
                    'driverName': order['name'],
                    'phone': order['phone'],
                    'photo': order['field7'],
                    'licenseNumber': order.get('field9'),
                    'createdAt': order['created_at'].isoformat() if order['created_at'] else None
                })
            
            result.sort(key=lambda x: x['createdAt'], reverse=True)
            
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
                    INSERT INTO sender_orders 
                    (pickup_address, pickup_comments, warehouse, delivery_date, cargo_type, 
                     cargo_quantity, sender_name, phone, photo_url, label_size)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at
                """, (
                    body.get('pickupAddress'),
                    body.get('pickupComments'),
                    body.get('warehouse'),
                    body.get('deliveryDate') or None,
                    body.get('cargoType'),
                    int(body.get('cargoQuantity')) if body.get('cargoQuantity') else None,
                    body.get('senderName'),
                    body.get('phone'),
                    body.get('photo'),
                    body.get('labelSize')
                ))
                
            elif order_type == 'carrier':
                cursor.execute("""
                    INSERT INTO carrier_orders 
                    (car_brand, car_model, license_plate, capacity_type, capacity_quantity,
                     warehouse, driver_name, phone, license_number, photo_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at
                """, (
                    body.get('carBrand'),
                    body.get('carModel'),
                    body.get('licensePlate'),
                    body.get('capacityType'),
                    int(body.get('capacityQuantity')) if body.get('capacityQuantity') else None,
                    body.get('warehouse'),
                    body.get('driverName'),
                    body.get('phone'),
                    body.get('licenseNumber'),
                    body.get('photo')
                ))
            else:
                cursor.close()
                conn.close()
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': 'Invalid order type'}),
                    'isBase64Encoded': False
                }
            
            result = cursor.fetchone()
            conn.commit()
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
            cursor.close()
            conn.close()
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