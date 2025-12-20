'''
Обработчики команд и сообщений для Telegram бота
'''

from database import *
from messaging import *
from utils import *
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import time

MARKETPLACES = [
    'Wildberries',
    'OZON',
    'Яндекс.Маркет',
    'AliExpress',
    'Другой'
]

user_states: Dict[int, Dict[str, Any]] = {}
admin_sessions: Dict[int, int] = {}


def show_main_menu(chat_id: int):
    """Показать главное меню выбора услуги"""
    user_states[chat_id] = {'step': 'choose_service', 'data': {}, 'last_activity': time.time()}
    
    templates = get_user_templates(chat_id)
    keyboard_buttons = [
        [{'text': '📦 Отправитель'}],
        [{'text': '🚚 Перевозчик'}],
        [{'text': '📋 Мои заявки'}]
    ]
    
    if templates:
        keyboard_buttons.append([{'text': '💾 Мои шаблоны'}])
        for template in templates[:5]:
            template_name = template['template_name']
            emoji = '📦' if template['order_type'] == 'sender' else '🚚'
            keyboard_buttons.insert(0, [{'text': f"{emoji} {template_name}"}])
    
    send_message(
        chat_id,
        "👋 <b>Добро пожаловать!</b>\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• Заявки отправителей удаляются через 5 дней после даты поставки\n"
        "• Сохраняйте скрины переписок\n"
        "• Сверяйте данные авто с заявкой\n\n"
        "<b>Выберите услугу:</b>",
        {
            'keyboard': keyboard_buttons,
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
    )


def handle_start(chat_id: int):
    """Обработчик команды /start"""
    show_main_menu(chat_id)


def handle_sender_start(chat_id: int):
    """Начать создание заявки отправителя"""
    clear_user_state(chat_id)
    state = get_user_state(chat_id)
    state['role'] = 'sender'
    state['step'] = 'marketplace'
    show_marketplace_selection(chat_id)


def show_marketplace_selection(chat_id: int):
    """Показать выбор маркетплейса"""
    keyboard_buttons = [[{'text': mp}] for mp in MARKETPLACES]
    
    send_message(
        chat_id,
        "📦 <b>Выберите маркетплейс</b>",
        {
            'keyboard': keyboard_buttons,
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
    )


def handle_carrier_start(chat_id: int):
    """Начать создание заявки перевозчика"""
    clear_user_state(chat_id)
    state = get_user_state(chat_id)
    state['role'] = 'carrier'
    state['step'] = 'warehouse'
    show_carrier_warehouse_selection(chat_id)


def show_carrier_warehouse_selection(chat_id: int):
    """Показать выбор склада для перевозчика"""
    send_message(
        chat_id,
        "📍 <b>Укажите склад назначения</b>\n\nНапример: Подольск или Коледино\nИли напишите 'Любой склад'",
        {
            'keyboard': [
                [{'text': 'Любой склад'}]
            ],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
    )


def show_preview(chat_id: int, data: Dict[str, Any]):
    """Показать превью заявки перед сохранением"""
    state = get_user_state(chat_id)
    role = state.get('role')
    
    if role == 'sender':
        preview_text = f"""
📦 <b>Проверьте данные заявки отправителя:</b>

📦 <b>Маркетплейс:</b> {data.get('marketplace')}
📍 <b>Склад:</b> {data.get('warehouse')}
📦 <b>Паллеты:</b> {data.get('pallet_quantity', 0)} шт
📦 <b>Коробки:</b> {data.get('box_quantity', 0)} шт
👤 <b>ФИО:</b> {data.get('sender_name')}
📱 <b>Телефон:</b> {data.get('phone')}
💵 <b>Ставка:</b> {data.get('rate')} руб
🏷️ <b>Термоэтикетка:</b> {data.get('label_size')} мм

📅 <b>Дата погрузки:</b> {data.get('loading_date')}
"""
    else:
        preview_text = f"""
🚚 <b>Проверьте данные заявки перевозчика:</b>

📍 <b>Склад:</b> {data.get('warehouse')}
🚗 <b>Авто:</b> {data.get('car_brand')} {data.get('car_model')}
🔢 <b>Гос. номер:</b> {data.get('license_plate')}
📦 <b>Вместимость паллет:</b> {data.get('pallet_capacity', 0)} шт
📦 <b>Вместимость коробок:</b> {data.get('box_capacity', 0)} шт
👤 <b>Водитель:</b> {data.get('driver_name')}
📱 <b>Телефон:</b> {data.get('phone')}
🚚 <b>Гидроборт:</b> {data.get('hydroboard')}

📅 <b>Дата погрузки:</b> {data.get('loading_date')}
📅 <b>Прибытие на склад:</b> {data.get('arrival_date')}
"""
    
    send_message(
        chat_id,
        preview_text,
        {
            'inline_keyboard': [
                [
                    {'text': '✅ Всё верно, сохранить', 'callback_data': f'save_{role}_order'},
                    {'text': '❌ Отменить', 'callback_data': 'cancel_order'}
                ]
            ]
        }
    )


def handle_save_sender_order(chat_id: int):
    """Сохранить заявку отправителя"""
    state = get_user_state(chat_id)
    data = state.get('data', {})
    data['chat_id'] = chat_id
    
    order_id = save_sender_order(data)
    
    if order_id:
        send_message(chat_id, f"✅ <b>Заявка #{order_id} создана!</b>")
        
        if data.get('label_size'):
            send_label_to_user(chat_id, order_id, 'sender', data['label_size'])
        
        notify_carriers_about_new_order(order_id, data)
        
        clear_user_state(chat_id)
        show_main_menu(chat_id)
    else:
        send_message(chat_id, "❌ Ошибка при создании заявки")


def handle_save_carrier_order(chat_id: int):
    """Сохранить заявку перевозчика"""
    state = get_user_state(chat_id)
    data = state.get('data', {})
    data['chat_id'] = chat_id
    
    order_id = save_carrier_order(data)
    
    if order_id:
        send_message(chat_id, f"✅ <b>Заявка #{order_id} создана!</b>")
        
        notify_senders_about_new_carrier(order_id, data)
        
        clear_user_state(chat_id)
        show_main_menu(chat_id)
    else:
        send_message(chat_id, "❌ Ошибка при создании заявки")


def handle_my_orders(chat_id: int):
    """Показать мои заявки"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 'sender' as type, id, marketplace, warehouse, loading_date, created_at
                FROM t_p52349012_telegram_bot_creatio.sender_orders
                WHERE chat_id = %s
                UNION ALL
                SELECT 'carrier' as type, id, 'N/A' as marketplace, warehouse, loading_date, created_at
                FROM t_p52349012_telegram_bot_creatio.carrier_orders
                WHERE chat_id = %s
                ORDER BY created_at DESC
                LIMIT 20
            """, (chat_id, chat_id))
            
            orders = cur.fetchall()
    finally:
        conn.close()
    
    if not orders:
        send_message(chat_id, "📭 <b>У вас пока нет заявок</b>\n\nВведите /start для создания новой заявки")
        return
    
    message = "📋 <b>Ваши заявки:</b>\n\n"
    buttons = []
    
    for order in orders:
        order_type = order['type']
        order_id = order['id']
        emoji = '📦' if order_type == 'sender' else '🚚'
        
        if order_type == 'sender':
            message += f"{emoji} #{order_id} | {order['marketplace']} → {order['warehouse']}\n"
        else:
            message += f"{emoji} #{order_id} | {order['warehouse']} | {order['loading_date']}\n"
        
        buttons.append([
            {'text': f'{emoji} Заявка #{order_id}', 'callback_data': f'view_{order_type}_{order_id}'}
        ])
    
    buttons.append([{'text': '🏠 Главное меню', 'callback_data': 'main_menu'}])
    
    send_message(
        chat_id,
        message,
        {'inline_keyboard': buttons}
    )


def handle_view_order(chat_id: int, order_type: str, order_id: int):
    """Показать детали заявки"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if order_type == 'sender':
                cur.execute("""
                    SELECT * FROM t_p52349012_telegram_bot_creatio.sender_orders
                    WHERE id = %s AND chat_id = %s
                """, (order_id, chat_id))
            else:
                cur.execute("""
                    SELECT * FROM t_p52349012_telegram_bot_creatio.carrier_orders
                    WHERE id = %s AND chat_id = %s
                """, (order_id, chat_id))
            
            order = cur.fetchone()
    finally:
        conn.close()
    
    if not order:
        send_message(chat_id, "❌ Заявка не найдена")
        return
    
    if order_type == 'sender':
        details = f"""
📦 <b>Заявка отправителя #{order_id}</b>

📦 <b>Маркетплейс:</b> {order.get('marketplace')}
📍 <b>Склад:</b> {order.get('warehouse')}
📦 <b>Паллеты:</b> {order.get('pallet_quantity', 0)} шт
📦 <b>Коробки:</b> {order.get('box_quantity', 0)} шт
👤 <b>ФИО:</b> {order.get('sender_name')}
📱 <b>Телефон:</b> {order.get('phone')}
💵 <b>Ставка:</b> {order.get('rate')} руб

📅 <b>Дата погрузки:</b> {order.get('loading_date')}
🕐 <b>Создана:</b> {order.get('created_at')}
"""
    else:
        details = f"""
🚚 <b>Заявка перевозчика #{order_id}</b>

📍 <b>Склад:</b> {order.get('warehouse')}
🚗 <b>Авто:</b> {order.get('car_brand')} {order.get('car_model')}
🔢 <b>Гос. номер:</b> {order.get('license_plate')}
📦 <b>Вместимость паллет:</b> {order.get('pallet_capacity', 0)} шт
📦 <b>Вместимость коробок:</b> {order.get('box_capacity', 0)} шт
👤 <b>Водитель:</b> {order.get('driver_name')}
📱 <b>Телефон:</b> {order.get('phone')}
🚚 <b>Гидроборт:</b> {order.get('hydroboard')}

📅 <b>Дата погрузки:</b> {order.get('loading_date')}
📅 <b>Прибытие:</b> {order.get('arrival_date')}
🕐 <b>Создана:</b> {order.get('created_at')}
"""
    
    send_message(
        chat_id,
        details,
        {
            'inline_keyboard': [
                [
                    {'text': '🗑 Удалить', 'callback_data': f'delete_{order_type}_{order_id}'}
                ],
                [
                    {'text': '◀️ Назад к заявкам', 'callback_data': 'my_orders'}
                ]
            ]
        }
    )


def handle_delete_order(chat_id: int, order_type: str, order_id: int, message_id: int):
    """Удалить заявку"""
    import psycopg2
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            if order_type == 'sender':
                cur.execute("""
                    DELETE FROM t_p52349012_telegram_bot_creatio.sender_orders
                    WHERE id = %s AND chat_id = %s
                """, (order_id, chat_id))
            else:
                cur.execute("""
                    DELETE FROM t_p52349012_telegram_bot_creatio.carrier_orders
                    WHERE id = %s AND chat_id = %s
                """, (order_id, chat_id))
            
            conn.commit()
            deleted = cur.rowcount > 0
    finally:
        conn.close()
    
    if deleted:
        edit_message(chat_id, message_id, f"✅ <b>Заявка #{order_id} удалена</b>")
        send_message(chat_id, "Используйте /start для возврата в главное меню")
    else:
        send_message(chat_id, "❌ Ошибка при удалении заявки")


def handle_cancel_order(chat_id: int, order_type: str, order_id: int):
    """Отменить удаление заявки"""
    handle_view_order(chat_id, order_type, order_id)


def handle_edit_order(chat_id: int, order_type: str, order_id: int):
    """Редактировать заявку"""
    send_message(chat_id, "⚠️ Редактирование заявок временно недоступно. Создайте новую заявку через /start")


def handle_save_edited_order(chat_id: int, order_type: str, order_id: int, field: str, value: str):
    """Сохранить отредактированную заявку"""
    import psycopg2
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            if order_type == 'sender':
                cur.execute(f"""
                    UPDATE t_p52349012_telegram_bot_creatio.sender_orders
                    SET {field} = %s
                    WHERE id = %s AND chat_id = %s
                """, (value, order_id, chat_id))
            else:
                cur.execute(f"""
                    UPDATE t_p52349012_telegram_bot_creatio.carrier_orders
                    SET {field} = %s
                    WHERE id = %s AND chat_id = %s
                """, (value, order_id, chat_id))
            
            conn.commit()
    finally:
        conn.close()
    
    send_message(chat_id, "✅ Заявка обновлена")
    handle_view_order(chat_id, order_type, order_id)


def handle_save_as_template(chat_id: int, order_type: str, order_id: int):
    """Сохранить заявку как шаблон"""
    send_message(chat_id, "💾 Введите название для шаблона:")
    state = get_user_state(chat_id)
    state['awaiting_template_name'] = True
    state['template_order_id'] = order_id
    state['template_order_type'] = order_type


def handle_use_template(chat_id: int):
    """Использовать шаблон"""
    templates = get_user_templates(chat_id)
    
    if not templates:
        send_message(chat_id, "📭 У вас пока нет сохранённых шаблонов")
        return
    
    message = "💾 <b>Выберите шаблон:</b>\n\n"
    buttons = []
    
    for template in templates:
        template_id = template['id']
        template_name = template['template_name']
        order_type = template['order_type']
        emoji = '📦' if order_type == 'sender' else '🚚'
        
        message += f"{emoji} {template_name}\n"
        buttons.append([
            {'text': f'{emoji} {template_name}', 'callback_data': f'load_template_{template_id}'}
        ])
    
    send_message(
        chat_id,
        message,
        {'inline_keyboard': buttons}
    )


def handle_manage_templates(chat_id: int):
    """Управление шаблонами"""
    templates = get_user_templates(chat_id)
    
    if not templates:
        send_message(
            chat_id,
            "📭 <b>У вас пока нет сохранённых шаблонов</b>\n\n"
            "Шаблоны создаются автоматически после создания заявки.\n"
            "Введите /start для создания новой заявки."
        )
        return
    
    message = "💾 <b>Ваши шаблоны:</b>\n\n"
    buttons = []
    
    for template in templates:
        template_id = template['id']
        template_name = template['template_name']
        order_type = template['order_type']
        emoji = '📦' if order_type == 'sender' else '🚚'
        
        message += f"{emoji} <b>{template_name}</b> ({order_type})\n"
        buttons.append([
            {'text': f'🗑 Удалить: {template_name}', 'callback_data': f'delete_template_{template_id}'}
        ])
    
    message += "\n💡 Нажмите на шаблон в главном меню чтобы использовать его"
    
    send_message(
        chat_id,
        message,
        {'inline_keyboard': buttons}
    )


def handle_delete_template(chat_id: int, template_id: int):
    """Удалить шаблон"""
    success = delete_template(chat_id, template_id)
    
    if success:
        send_message(chat_id, "✅ Шаблон удалён")
        handle_manage_templates(chat_id)
    else:
        send_message(chat_id, "❌ Ошибка при удалении шаблона")


def handle_load_template(chat_id: int, template_id: int):
    """Загрузить шаблон"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT template_data, order_type
                FROM t_p52349012_telegram_bot_creatio.order_templates
                WHERE id = %s AND chat_id = %s
            """, (template_id, chat_id))
            
            result = cur.fetchone()
    finally:
        conn.close()
    
    if not result:
        send_message(chat_id, "❌ Шаблон не найден")
        return
    
    template_data = result['template_data']
    order_type = result['order_type']
    
    state = get_user_state(chat_id)
    state['role'] = order_type
    state['data'] = template_data
    state['step'] = 'show_preview'
    
    show_preview(chat_id, template_data)


def handle_text_message(chat_id: int, text: str):
    """Обработка текстовых сообщений"""
    if not validate_text_length(text):
        send_message(chat_id, f"❌ Сообщение слишком длинное. Максимум {MAX_TEXT_LENGTH} символов.")
        return
    
    state = get_user_state(chat_id)
    step = state.get('step', '')
    data = state.get('data', {})
    
    if text == '📦 Отправитель':
        handle_sender_start(chat_id)
        return
    elif text == '🚚 Перевозчик':
        handle_carrier_start(chat_id)
        return
    elif text == '📋 Мои заявки':
        handle_my_orders(chat_id)
        return
    elif text == '💾 Мои шаблоны':
        handle_manage_templates(chat_id)
        return
    
    templates = get_user_templates(chat_id)
    for template in templates:
        template_name = template['template_name']
        if template_name in text:
            handle_load_template(chat_id, template['id'])
            return
    
    if step == 'marketplace':
        if text in MARKETPLACES:
            data['marketplace'] = text
            state['step'] = 'sender_warehouse'
            send_message(chat_id, "📍 <b>Укажите склад отгрузки</b>\n\nНапример: Подольск или Коледино", {'remove_keyboard': True})
        else:
            send_message(chat_id, "❌ Выберите маркетплейс из списка")
    
    elif step == 'sender_warehouse':
        data['warehouse'] = text
        state['step'] = 'sender_loading_date'
        
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        
        send_message(
            chat_id,
            "📅 <b>Укажите желаемую дату ПОГРУЗКИ</b>\n\nВыберите из вариантов или введите дату вручную\nФормат: ДД.ММ.ГГГГ",
            {
                'keyboard': [
                    [{'text': f'🔴 Сегодня ({today.strftime("%d.%m.%Y")})'}],
                    [{'text': f'🟢 Завтра ({tomorrow.strftime("%d.%m.%Y")})'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'sender_loading_date':
        try:
            if 'сегодня' in text.lower() or '🔴' in text:
                loading_date = datetime.now()
            elif 'завтра' in text.lower() or '🟢' in text:
                loading_date = datetime.now() + timedelta(days=1)
            else:
                text_cleaned = text.replace('🔴', '').replace('🟢', '').strip()
                text_cleaned = text_cleaned.split('(')[-1].replace(')', '').strip() if '(' in text_cleaned else text_cleaned
                loading_date = datetime.strptime(text_cleaned, '%d.%m.%Y')
            
            data['loading_date'] = loading_date.strftime('%Y-%m-%d')
            state['step'] = 'sender_pallet_quantity'
            send_message(chat_id, "📦 <b>Укажите количество паллет</b>\n\nНапример: 5\nИли 0, если нет паллет")
        except ValueError:
            send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
    
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
        phone = text.strip()
        if phone.startswith('8'):
            phone = '+7' + phone[1:]
        elif not phone.startswith('+'):
            phone = '+7' + phone
        data['phone'] = phone
        state['step'] = 'sender_rate'
        send_message(chat_id, "💵 <b>Укажите желаемую ставку в рублях</b>\n\nНапример: 5000", {'remove_keyboard': True})
    
    elif step == 'sender_rate':
        if text.isdigit():
            data['rate'] = int(text)
            state['step'] = 'sender_label_size'
            send_message(
                chat_id,
                "🏷️ <b>Выберите термоэтикетку с инфо для водителя</b>",
                {
                    'keyboard': [
                        [{'text': '120x75 мм'}],
                        [{'text': '58x40 мм'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
            )
        else:
            send_message(chat_id, "❌ Неверный формат. Укажите цифру. Например: 5000")
    
    elif step == 'sender_label_size':
        if '120' in text:
            data['label_size'] = '120x75'
        else:
            data['label_size'] = '58x40'
        
        send_message(chat_id, "📋 Термоэтикетка будет отправлена после создания заявки")
        state['step'] = 'show_preview'
        show_preview(chat_id, data)
    
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
        phone = text.strip()
        if phone.startswith('8'):
            phone = '+7' + phone[1:]
        elif not phone.startswith('+'):
            phone = '+7' + phone
        data['phone'] = phone
        state['step'] = 'carrier_hydroboard'
        send_message(
            chat_id,
            "🚚 <b>Гидроборт</b>",
            {
                'keyboard': [
                    [{'text': 'Есть'}],
                    [{'text': 'Нету'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'carrier_hydroboard':
        data['hydroboard'] = 'Есть' if 'есть' in text.lower() else 'Нету'
        state['step'] = 'carrier_loading_date'
        
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        
        send_message(
            chat_id,
            "📅 <b>Укажите желаемую дату ПОГРУЗКИ</b>\n\nВыберите из вариантов или введите дату вручную\nФормат: ДД.ММ.ГГГГ",
            {
                'keyboard': [
                    [{'text': f'🔴 Сегодня ({today.strftime("%d.%m.%Y")})'}],
                    [{'text': f'🟢 Завтра ({tomorrow.strftime("%d.%m.%Y")})'}]
                ],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
        )
    
    elif step == 'carrier_loading_date':
        try:
            if 'сегодня' in text.lower() or '🔴' in text:
                loading_date = datetime.now()
            elif 'завтра' in text.lower() or '🟢' in text:
                loading_date = datetime.now() + timedelta(days=1)
            else:
                text_cleaned = text.replace('🔴', '').replace('🟢', '').strip()
                text_cleaned = text_cleaned.split('(')[-1].replace(')', '').strip() if '(' in text_cleaned else text_cleaned
                loading_date = datetime.strptime(text_cleaned, '%d.%m.%Y')
            
            data['loading_date'] = loading_date.strftime('%Y-%m-%d')
            state['step'] = 'carrier_arrival_date'
            
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            
            send_message(
                chat_id,
                "📅 <b>Укажите дату прибытия на склад</b>\n\nВыберите из вариантов или введите дату вручную\nФормат: ДД.ММ.ГГГГ",
                {
                    'keyboard': [
                        [{'text': f'🔴 Сегодня ({today.strftime("%d.%m.%Y")})'}],
                        [{'text': f'🟢 Завтра ({tomorrow.strftime("%d.%m.%Y")})'}]
                    ],
                    'resize_keyboard': True,
                    'one_time_keyboard': True
                }
            )
        except ValueError:
            send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
    
    elif step == 'carrier_arrival_date':
        try:
            if 'сегодня' in text.lower() or '🔴' in text:
                arrival_date = datetime.now()
            elif 'завтра' in text.lower() or '🟢' in text:
                arrival_date = datetime.now() + timedelta(days=1)
            else:
                text_cleaned = text.replace('🔴', '').replace('🟢', '').strip()
                text_cleaned = text_cleaned.split('(')[-1].replace(')', '').strip() if '(' in text_cleaned else text_cleaned
                arrival_date = datetime.strptime(text_cleaned, '%d.%m.%Y')
            
            data['arrival_date'] = arrival_date.strftime('%Y-%m-%d')
            state['step'] = 'show_preview'
            show_preview(chat_id, data)
        except ValueError:
            send_message(chat_id, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")


def handle_callback_query(chat_id: int, data: str, message_id: int):
    """Обработка callback query"""
    answer_callback_query(data)
    
    if data == 'sender_start':
        handle_sender_start(chat_id)
    elif data == 'carrier_start':
        handle_carrier_start(chat_id)
    elif data == 'my_orders':
        handle_my_orders(chat_id)
    elif data.startswith('view_'):
        parts = data.split('_')
        order_type = parts[1]
        order_id = int(parts[2])
        handle_view_order(chat_id, order_type, order_id)
    elif data.startswith('delete_') and not data.startswith('delete_template_'):
        parts = data.split('_')
        order_type = parts[1]
        order_id = int(parts[2])
        handle_delete_order(chat_id, order_type, order_id, message_id)
    elif data.startswith('cancel_'):
        parts = data.split('_')
        order_type = parts[1]
        order_id = int(parts[2])
        handle_cancel_order(chat_id, order_type, order_id)
    elif data == 'save_sender_order':
        handle_save_sender_order(chat_id)
    elif data == 'save_carrier_order':
        handle_save_carrier_order(chat_id)
    elif data.startswith('load_template_'):
        template_id = int(data.split('_')[2])
        handle_load_template(chat_id, template_id)
    elif data.startswith('delete_template_'):
        template_id = int(data.split('_')[2])
        handle_delete_template(chat_id, template_id)
    elif data == 'main_menu':
        show_main_menu(chat_id)
    elif data == 'admin_panel':
        handle_admin_panel(chat_id)
    elif data == 'admin_stats':
        handle_admin_stats(chat_id)
    elif data == 'admin_orders':
        handle_admin_orders(chat_id)
    elif data.startswith('admin_remove_order_'):
        parts = data.split('_')
        order_type = parts[3]
        order_id = int(parts[4])
        handle_admin_remove_order(chat_id, order_type, order_id, message_id)
    elif data == 'admin_users':
        handle_admin_users(chat_id)
    elif data.startswith('admin_user_'):
        user_chat_id = int(data.split('_')[2])
        handle_admin_user_detail(chat_id, user_chat_id)
    elif data.startswith('admin_block_'):
        user_chat_id = int(data.split('_')[2])
        handle_admin_block_user(chat_id, user_chat_id, message_id)
    elif data.startswith('admin_unblock_'):
        user_chat_id = int(data.split('_')[2])
        handle_admin_unblock_user(chat_id, user_chat_id, message_id)
    elif data == 'admin_security_logs':
        handle_admin_security_logs(chat_id)
    elif data.startswith('admin_user_orders_'):
        user_chat_id = int(data.split('_')[3])
        handle_admin_user_orders(chat_id, user_chat_id)
    else:
        send_message(chat_id, "❌ Неизвестная команда")


def handle_admin_panel(chat_id: int):
    """Админ-панель"""
    perms = get_admin_permissions(chat_id)
    
    if not perms:
        send_message(chat_id, "❌ У вас нет прав администратора")
        return
    
    buttons = []
    
    if perms.get('can_view_stats'):
        buttons.append([{'text': '📊 Статистика', 'callback_data': 'admin_stats'}])
    
    if perms.get('can_view_orders'):
        buttons.append([{'text': '📋 Все заявки', 'callback_data': 'admin_orders'}])
    
    if perms.get('can_manage_users'):
        buttons.append([{'text': '👥 Пользователи', 'callback_data': 'admin_users'}])
    
    if perms.get('can_view_security_logs'):
        buttons.append([{'text': '🔒 Логи безопасности', 'callback_data': 'admin_security_logs'}])
    
    buttons.append([{'text': '🏠 Главное меню', 'callback_data': 'main_menu'}])
    
    send_message(
        chat_id,
        f"👑 <b>Админ-панель</b>\n\n🔑 Роль: {perms.get('role')}",
        {'inline_keyboard': buttons}
    )


def handle_admin_stats(chat_id: int):
    """Статистика для админа"""
    import psycopg2
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_view_stats'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.sender_orders")
            sender_orders = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.carrier_orders")
            carrier_orders = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(DISTINCT chat_id) FROM t_p52349012_telegram_bot_creatio.sender_orders")
            sender_users = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(DISTINCT chat_id) FROM t_p52349012_telegram_bot_creatio.carrier_orders")
            carrier_users = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.blocked_users")
            blocked_users = cur.fetchone()[0]
    finally:
        conn.close()
    
    message = f"""
📊 <b>Статистика бота</b>

📦 <b>Заявки отправителей:</b> {sender_orders}
🚚 <b>Заявки перевозчиков:</b> {carrier_orders}
👥 <b>Отправителей:</b> {sender_users}
👥 <b>Перевозчиков:</b> {carrier_users}
🚫 <b>Заблокировано:</b> {blocked_users}
"""
    
    send_message(
        chat_id,
        message,
        {
            'inline_keyboard': [
                [{'text': '◀️ Назад', 'callback_data': 'admin_panel'}]
            ]
        }
    )


def handle_admin_orders(chat_id: int):
    """Все заявки для админа"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_view_orders'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 'sender' as type, id, chat_id, marketplace, warehouse, created_at
                FROM t_p52349012_telegram_bot_creatio.sender_orders
                UNION ALL
                SELECT 'carrier' as type, id, chat_id, 'N/A' as marketplace, warehouse, created_at
                FROM t_p52349012_telegram_bot_creatio.carrier_orders
                ORDER BY created_at DESC
                LIMIT 50
            """)
            
            orders = cur.fetchall()
    finally:
        conn.close()
    
    if not orders:
        send_message(chat_id, "📭 Заявок пока нет")
        return
    
    message = "📋 <b>Последние заявки:</b>\n\n"
    buttons = []
    
    for order in orders:
        order_type = order['type']
        order_id = order['id']
        emoji = '📦' if order_type == 'sender' else '🚚'
        
        message += f"{emoji} #{order_id} | User: {order['chat_id']}\n"
        
        if perms.get('can_remove_orders'):
            buttons.append([
                {'text': f'🗑 Удалить #{order_id}', 'callback_data': f'admin_remove_order_{order_type}_{order_id}'}
            ])
    
    buttons.append([{'text': '◀️ Назад', 'callback_data': 'admin_panel'}])
    
    send_message(
        chat_id,
        message,
        {'inline_keyboard': buttons}
    )


def handle_admin_remove_order(chat_id: int, order_type: str, order_id: int, message_id: int):
    """Удалить заявку (админ)"""
    import psycopg2
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_remove_orders'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            if order_type == 'sender':
                cur.execute("DELETE FROM t_p52349012_telegram_bot_creatio.sender_orders WHERE id = %s", (order_id,))
            else:
                cur.execute("DELETE FROM t_p52349012_telegram_bot_creatio.carrier_orders WHERE id = %s", (order_id,))
            
            conn.commit()
            deleted = cur.rowcount > 0
    finally:
        conn.close()
    
    if deleted:
        edit_message(chat_id, message_id, f"✅ Заявка #{order_id} удалена администратором")
    else:
        send_message(chat_id, "❌ Ошибка при удалении")


def handle_admin_users(chat_id: int):
    """Список пользователей"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_manage_users'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT chat_id, COUNT(*) as order_count
                FROM (
                    SELECT chat_id FROM t_p52349012_telegram_bot_creatio.sender_orders
                    UNION ALL
                    SELECT chat_id FROM t_p52349012_telegram_bot_creatio.carrier_orders
                ) AS combined
                GROUP BY chat_id
                ORDER BY order_count DESC
                LIMIT 30
            """)
            
            users = cur.fetchall()
    finally:
        conn.close()
    
    message = "👥 <b>Активные пользователи:</b>\n\n"
    buttons = []
    
    for user in users:
        user_chat_id = user['chat_id']
        order_count = user['order_count']
        
        message += f"👤 {user_chat_id} | Заявок: {order_count}\n"
        buttons.append([
            {'text': f'👤 {user_chat_id}', 'callback_data': f'admin_user_{user_chat_id}'}
        ])
    
    buttons.append([{'text': '◀️ Назад', 'callback_data': 'admin_panel'}])
    
    send_message(
        chat_id,
        message,
        {'inline_keyboard': buttons}
    )


def handle_admin_user_detail(chat_id: int, user_chat_id: int):
    """Детали пользователя"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_manage_users'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.sender_orders
                WHERE chat_id = %s
            """, (user_chat_id,))
            sender_orders = cur.fetchone()['count']
            
            cur.execute("""
                SELECT COUNT(*) FROM t_p52349012_telegram_bot_creatio.carrier_orders
                WHERE chat_id = %s
            """, (user_chat_id,))
            carrier_orders = cur.fetchone()['count']
            
            cur.execute("""
                SELECT * FROM t_p52349012_telegram_bot_creatio.blocked_users
                WHERE chat_id = %s
            """, (user_chat_id,))
            is_blocked = cur.fetchone() is not None
    finally:
        conn.close()
    
    message = f"""
👤 <b>Пользователь {user_chat_id}</b>

📦 <b>Заявок отправителя:</b> {sender_orders}
🚚 <b>Заявок перевозчика:</b> {carrier_orders}
🚫 <b>Заблокирован:</b> {'Да' if is_blocked else 'Нет'}
"""
    
    buttons = []
    
    if perms.get('can_block_users'):
        if is_blocked:
            buttons.append([{'text': '✅ Разблокировать', 'callback_data': f'admin_unblock_{user_chat_id}'}])
        else:
            buttons.append([{'text': '🚫 Заблокировать', 'callback_data': f'admin_block_{user_chat_id}'}])
    
    buttons.append([{'text': '📋 Заявки пользователя', 'callback_data': f'admin_user_orders_{user_chat_id}'}])
    buttons.append([{'text': '◀️ Назад', 'callback_data': 'admin_users'}])
    
    send_message(
        chat_id,
        message,
        {'inline_keyboard': buttons}
    )


def handle_admin_block_user(chat_id: int, user_chat_id: int, message_id: int):
    """Заблокировать пользователя"""
    import psycopg2
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_block_users'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO t_p52349012_telegram_bot_creatio.blocked_users (chat_id)
                VALUES (%s)
                ON CONFLICT (chat_id) DO NOTHING
            """, (user_chat_id,))
            
            conn.commit()
    finally:
        conn.close()
    
    log_security_event(chat_id, 'admin_block', f'Admin {chat_id} blocked user {user_chat_id}', 'high')
    edit_message(chat_id, message_id, f"✅ Пользователь {user_chat_id} заблокирован")


def handle_admin_unblock_user(chat_id: int, user_chat_id: int, message_id: int):
    """Разблокировать пользователя"""
    import psycopg2
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_block_users'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM t_p52349012_telegram_bot_creatio.blocked_users
                WHERE chat_id = %s
            """, (user_chat_id,))
            
            conn.commit()
    finally:
        conn.close()
    
    log_security_event(chat_id, 'admin_unblock', f'Admin {chat_id} unblocked user {user_chat_id}', 'medium')
    edit_message(chat_id, message_id, f"✅ Пользователь {user_chat_id} разблокирован")


def handle_admin_set_limit(chat_id: int, user_chat_id: int, limit: int):
    """Установить лимит для пользователя"""
    import psycopg2
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_manage_users'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO t_p52349012_telegram_bot_creatio.user_limits (chat_id, daily_order_limit)
                VALUES (%s, %s)
                ON CONFLICT (chat_id) DO UPDATE SET daily_order_limit = EXCLUDED.daily_order_limit
            """, (user_chat_id, limit))
            
            conn.commit()
    finally:
        conn.close()
    
    send_message(chat_id, f"✅ Лимит для пользователя {user_chat_id} установлен: {limit} заявок/день")


def handle_admin_security_logs(chat_id: int):
    """Логи безопасности"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_view_security_logs'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM t_p52349012_telegram_bot_creatio.security_logs
                ORDER BY created_at DESC
                LIMIT 50
            """)
            
            logs = cur.fetchall()
    finally:
        conn.close()
    
    if not logs:
        send_message(chat_id, "📭 Логов пока нет")
        return
    
    message = "🔒 <b>Логи безопасности:</b>\n\n"
    
    for log in logs[:20]:
        message += f"⚠️ {log['severity']} | {log['event_type']}\n"
        message += f"👤 User: {log['chat_id']}\n"
        message += f"📋 {log['details']}\n\n"
    
    send_message(
        chat_id,
        message,
        {
            'inline_keyboard': [
                [{'text': '◀️ Назад', 'callback_data': 'admin_panel'}]
            ]
        }
    )


def handle_admin_user_orders(chat_id: int, user_chat_id: int):
    """Заявки конкретного пользователя"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    perms = get_admin_permissions(chat_id)
    
    if not perms or not perms.get('can_view_orders'):
        send_message(chat_id, "❌ Недостаточно прав")
        return
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 'sender' as type, id, marketplace, warehouse, created_at
                FROM t_p52349012_telegram_bot_creatio.sender_orders
                WHERE chat_id = %s
                UNION ALL
                SELECT 'carrier' as type, id, 'N/A' as marketplace, warehouse, created_at
                FROM t_p52349012_telegram_bot_creatio.carrier_orders
                WHERE chat_id = %s
                ORDER BY created_at DESC
                LIMIT 30
            """, (user_chat_id, user_chat_id))
            
            orders = cur.fetchall()
    finally:
        conn.close()
    
    if not orders:
        send_message(chat_id, "📭 У пользователя нет заявок")
        return
    
    message = f"📋 <b>Заявки пользователя {user_chat_id}:</b>\n\n"
    
    for order in orders:
        order_type = order['type']
        order_id = order['id']
        emoji = '📦' if order_type == 'sender' else '🚚'
        
        message += f"{emoji} #{order_id} | {order['warehouse']}\n"
    
    send_message(
        chat_id,
        message,
        {
            'inline_keyboard': [
                [{'text': '◀️ Назад', 'callback_data': f'admin_user_{user_chat_id}'}]
            ]
        }
    )
