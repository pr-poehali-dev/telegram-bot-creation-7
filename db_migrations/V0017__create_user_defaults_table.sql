-- Таблица для хранения последних значений пользователя (умные дефолты)
CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.user_defaults (
    chat_id BIGINT PRIMARY KEY,
    
    -- Общие поля
    last_marketplace VARCHAR(100),
    last_warehouse VARCHAR(200),
    last_phone VARCHAR(20),
    
    -- Для отправителей
    last_sender_name VARCHAR(200),
    last_loading_city VARCHAR(100),
    last_loading_address TEXT,
    
    -- Для перевозчиков
    last_driver_name VARCHAR(200),
    last_car_model VARCHAR(100),
    last_license_plate VARCHAR(20),
    last_loading_city_carrier VARCHAR(100),
    last_hydroboard VARCHAR(10), -- 'Есть' или 'Нету'
    
    -- Метаданные
    last_order_type VARCHAR(20), -- 'sender' или 'carrier'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрого доступа
CREATE INDEX IF NOT EXISTS idx_user_defaults_chat_id ON t_p52349012_telegram_bot_creatio.user_defaults(chat_id);
CREATE INDEX IF NOT EXISTS idx_user_defaults_order_type ON t_p52349012_telegram_bot_creatio.user_defaults(last_order_type);

COMMENT ON TABLE t_p52349012_telegram_bot_creatio.user_defaults IS 'Кэш последних значений пользователя для быстрого создания новых заявок';