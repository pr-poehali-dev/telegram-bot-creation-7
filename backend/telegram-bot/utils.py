"""
Утилиты и вспомогательные функции
"""

import time
import ipaddress
from typing import Dict
from collections import defaultdict

from constants import (
    TELEGRAM_IPS, MAX_REQUESTS_PER_MINUTE, MAX_TEXT_LENGTH,
    SESSION_TIMEOUT, ADMIN_SESSION_TIMEOUT
)

user_states: Dict[int, Dict[str, any]] = {}
admin_sessions: Dict[int, int] = {}
request_counts: Dict[int, list] = defaultdict(list)

def is_telegram_request(ip: str) -> bool:
    if not ip:
        return True
    try:
        ip_addr = ipaddress.ip_address(ip)
        for cidr in TELEGRAM_IPS:
            if ip_addr in ipaddress.ip_network(cidr):
                return True
        return False
    except:
        return True

def is_rate_limited(chat_id: int) -> bool:
    now = time.time()
    requests_list = request_counts[chat_id]
    
    requests_list = [req for req in requests_list if now - req < 60]
    request_counts[chat_id] = requests_list
    
    if len(requests_list) >= MAX_REQUESTS_PER_MINUTE:
        return True
    
    requests_list.append(now)
    return False

def validate_text_length(text: str, max_length: int = MAX_TEXT_LENGTH) -> bool:
    return len(text) <= max_length

def get_user_state(chat_id: int) -> dict:
    return user_states.get(chat_id, {})

def set_user_state(chat_id: int, state: dict):
    user_states[chat_id] = state

def clear_user_state(chat_id: int):
    if chat_id in user_states:
        del user_states[chat_id]

def check_admin_session(chat_id: int) -> bool:
    if chat_id in admin_sessions:
        session_time = admin_sessions[chat_id]
        if time.time() - session_time < ADMIN_SESSION_TIMEOUT:
            return True
        else:
            del admin_sessions[chat_id]
    return False

def create_admin_session(chat_id: int):
    admin_sessions[chat_id] = int(time.time())