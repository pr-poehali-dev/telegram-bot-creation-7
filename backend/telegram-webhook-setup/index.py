'''
Бизнес: Автоматическая настройка webhook для Telegram бота
Аргументы: event - dict с httpMethod GET
Возвращает: Статус настройки webhook
'''

import json
import os
from typing import Dict, Any
import requests

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
WEBHOOK_URL = 'https://functions.poehali.dev/f0b965eb-584a-4631-8fb2-6189ea6726e0'

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method: str = event.get('httpMethod', 'GET')
    query_params = event.get('queryStringParameters', {})
    action = query_params.get('action', 'setup')
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }
    
    if not BOT_TOKEN:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': 'TELEGRAM_BOT_TOKEN не установлен в секретах'
            }),
            'isBase64Encoded': False
        }
    
    if action == 'delete':
        try:
            response = requests.post(
                f'https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook',
                json={'drop_pending_updates': True}
            )
            result = response.json()
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': True,
                    'message': 'Webhook удален и pending updates очищены',
                    'result': result
                }),
                'isBase64Encoded': False
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': str(e)
                }),
                'isBase64Encoded': False
            }
    
    if action == 'info':
        try:
            response = requests.get(
                f'https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo'
            )
            result = response.json()
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result),
                'isBase64Encoded': False
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': str(e)
                }),
                'isBase64Encoded': False
            }
    
    try:
        response = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/setWebhook',
            json={
                'url': WEBHOOK_URL,
                'drop_pending_updates': True
            }
        )
        
        result = response.json()
        
        if result.get('ok'):
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': True,
                    'message': 'Webhook успешно настроен!',
                    'webhook_url': WEBHOOK_URL,
                    'bot_info': result.get('description', '')
                }),
                'isBase64Encoded': False
            }
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': result.get('description', 'Неизвестная ошибка')
                }),
                'isBase64Encoded': False
            }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': str(e)
            }),
            'isBase64Encoded': False
        }