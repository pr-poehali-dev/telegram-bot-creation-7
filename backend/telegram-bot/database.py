"""
Модуль для работы с базой данных
Все функции SQL-запросов к PostgreSQL
"""

import os
import json
from typing import Dict, Any, Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

# Импорт констант
MAX_ORDERS_PER_DAY = 10

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

def get_admin_permissions(chat_id: int) -> Optional[Dict[str, bool]]:
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
    return get_admin_permissions(chat_id) is not None

def check_suspicious_activity(chat_id: int) -> bool:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.security_logs
                WHERE chat_id = %s AND created_at > NOW() - INTERVAL '1 hour'
            """, (chat_id,))
            
            events_last_hour = cur.fetchone()[0]
            
            if events_last_hour > 50:
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
                return True
            
            return False
    except:
        return False
    finally:
        conn.close()

def save_warehouse_mapping(normalized_name: str, original_name: str):
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO t_p52349012_telegram_bot_creatio.warehouse_mappings 
                (normalized_name, original_name)
                VALUES (%s, %s)
                ON CONFLICT (normalized_name, original_name) DO UPDATE 
                SET usage_count = t_p52349012_telegram_bot_creatio.warehouse_mappings.usage_count + 1
            """, (normalized_name, original_name))
            conn.commit()
        conn.close()
    except:
        pass

def save_sender_order(chat_id: int, order_data: Dict[str, Any]) -> int:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO t_p52349012_telegram_bot_creatio.sender_orders 
                (chat_id, marketplace, from_warehouse, to_warehouse, pallets_count, 
                 cargo_type, shipping_date, additional_info, username, first_name, last_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                chat_id,
                order_data.get('marketplace'),
                order_data.get('from_warehouse'),
                order_data.get('to_warehouse'),
                order_data.get('pallets_count'),
                order_data.get('cargo_type'),
                order_data.get('shipping_date'),
                order_data.get('additional_info'),
                order_data.get('username'),
                order_data.get('first_name'),
                order_data.get('last_name')
            ))
            order_id = cur.fetchone()[0]
            conn.commit()
            
            normalized_from = normalize_warehouse(order_data.get('from_warehouse', ''))
            normalized_to = normalize_warehouse(order_data.get('to_warehouse', ''))
            
            if normalized_from:
                save_warehouse_mapping(normalized_from, order_data.get('from_warehouse'))
            if normalized_to:
                save_warehouse_mapping(normalized_to, order_data.get('to_warehouse'))
            
            return order_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def save_carrier_order(chat_id: int, order_data: Dict[str, Any]) -> int:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO t_p52349012_telegram_bot_creatio.carrier_orders 
                (chat_id, from_warehouse, to_warehouse, truck_type, price, 
                 additional_info, username, first_name, last_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                chat_id,
                order_data.get('from_warehouse'),
                order_data.get('to_warehouse'),
                order_data.get('truck_type'),
                order_data.get('price'),
                order_data.get('additional_info'),
                order_data.get('username'),
                order_data.get('first_name'),
                order_data.get('last_name')
            ))
            order_id = cur.fetchone()[0]
            conn.commit()
            
            normalized_from = normalize_warehouse(order_data.get('from_warehouse', ''))
            normalized_to = normalize_warehouse(order_data.get('to_warehouse', ''))
            
            if normalized_from:
                save_warehouse_mapping(normalized_from, order_data.get('from_warehouse'))
            if normalized_to:
                save_warehouse_mapping(normalized_to, order_data.get('to_warehouse'))
            
            return order_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_user_orders(chat_id: int, order_type: str = 'all') -> List[Dict[str, Any]]:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if order_type == 'sender':
                cur.execute("""
                    SELECT id, 'sender' as type, marketplace, from_warehouse, to_warehouse, 
                           pallets_count, cargo_type, shipping_date, additional_info, created_at
                    FROM t_p52349012_telegram_bot_creatio.sender_orders
                    WHERE chat_id = %s
                    ORDER BY created_at DESC
                    LIMIT 20
                """, (chat_id,))
            elif order_type == 'carrier':
                cur.execute("""
                    SELECT id, 'carrier' as type, from_warehouse, to_warehouse, 
                           truck_type, price, additional_info, created_at
                    FROM t_p52349012_telegram_bot_creatio.carrier_orders
                    WHERE chat_id = %s
                    ORDER BY created_at DESC
                    LIMIT 20
                """, (chat_id,))
            else:
                cur.execute("""
                    SELECT id, 'sender' as type, marketplace, from_warehouse, to_warehouse, 
                           pallets_count, cargo_type, shipping_date, additional_info, created_at
                    FROM t_p52349012_telegram_bot_creatio.sender_orders
                    WHERE chat_id = %s
                    UNION ALL
                    SELECT id, 'carrier' as type, NULL as marketplace, from_warehouse, to_warehouse, 
                           NULL as pallets_count, truck_type as cargo_type, NULL as shipping_date, 
                           additional_info, created_at
                    FROM t_p52349012_telegram_bot_creatio.carrier_orders
                    WHERE chat_id = %s
                    ORDER BY created_at DESC
                    LIMIT 20
                """, (chat_id, chat_id))
            
            return [dict(row) for row in cur.fetchall()]
    except:
        return []
    finally:
        conn.close()

def get_order_by_id(order_id: int, order_type: str) -> Optional[Dict[str, Any]]:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if order_type == 'sender':
                cur.execute("""
                    SELECT * FROM t_p52349012_telegram_bot_creatio.sender_orders
                    WHERE id = %s
                """, (order_id,))
            else:
                cur.execute("""
                    SELECT * FROM t_p52349012_telegram_bot_creatio.carrier_orders
                    WHERE id = %s
                """, (order_id,))
            
            result = cur.fetchone()
            return dict(result) if result else None
    except:
        return None
    finally:
        conn.close()

def update_order(order_id: int, order_type: str, field: str, value: Any) -> bool:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        table = 't_p52349012_telegram_bot_creatio.sender_orders' if order_type == 'sender' else 't_p52349012_telegram_bot_creatio.carrier_orders'
        
        with conn.cursor() as cur:
            query = f"UPDATE {table} SET {field} = %s WHERE id = %s"
            cur.execute(query, (value, order_id))
            conn.commit()
            return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_order(order_id: int, order_type: str) -> bool:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        table = 't_p52349012_telegram_bot_creatio.sender_orders' if order_type == 'sender' else 't_p52349012_telegram_bot_creatio.carrier_orders'
        
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {table} WHERE id = %s", (order_id,))
            conn.commit()
            return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()

def save_template(chat_id: int, template_name: str, template_data: Dict[str, Any]) -> bool:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO t_p52349012_telegram_bot_creatio.order_templates 
                (chat_id, template_name, template_type, template_data)
                VALUES (%s, %s, %s, %s)
            """, (
                chat_id,
                template_name,
                template_data.get('type', 'sender'),
                json.dumps(template_data)
            ))
            conn.commit()
            return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()

def get_user_templates(chat_id: int) -> List[Dict[str, Any]]:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, template_name, template_type, template_data, created_at
                FROM t_p52349012_telegram_bot_creatio.order_templates
                WHERE chat_id = %s
                ORDER BY created_at DESC
            """, (chat_id,))
            
            return [dict(row) for row in cur.fetchall()]
    except:
        return []
    finally:
        conn.close()

def delete_template(template_id: int) -> bool:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM t_p52349012_telegram_bot_creatio.order_templates
                WHERE id = %s
            """, (template_id,))
            conn.commit()
            return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()

def get_template_by_id(template_id: int) -> Optional[Dict[str, Any]]:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM t_p52349012_telegram_bot_creatio.order_templates
                WHERE id = %s
            """, (template_id,))
            
            result = cur.fetchone()
            return dict(result) if result else None
    except:
        return None
    finally:
        conn.close()

def get_matching_warehouses(search_term: str, limit: int = 5) -> List[str]:
    normalized_search = normalize_warehouse(search_term)
    
    if not normalized_search:
        return []
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT original_name, usage_count
                FROM t_p52349012_telegram_bot_creatio.warehouse_mappings
                WHERE normalized_name LIKE %s
                ORDER BY usage_count DESC, original_name
                LIMIT %s
            """, (f'%{normalized_search}%', limit))
            
            return [row[0] for row in cur.fetchall()]
    except:
        return []
    finally:
        conn.close()

def update_user_info(chat_id: int, username: str, first_name: str, last_name: str):
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO t_p52349012_telegram_bot_creatio.users 
                (chat_id, username, first_name, last_name, last_seen)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (chat_id) DO UPDATE 
                SET username = %s, first_name = %s, last_name = %s, last_seen = CURRENT_TIMESTAMP
            """, (chat_id, username, first_name, last_name, username, first_name, last_name))
            conn.commit()
        conn.close()
    except:
        pass
