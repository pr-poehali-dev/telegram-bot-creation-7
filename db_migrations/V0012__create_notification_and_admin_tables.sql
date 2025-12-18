-- Таблица для настроек уведомлений пользователей
CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.notification_settings (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL UNIQUE,
    -- Уведомления о встречных грузах
    notify_matching_orders BOOLEAN DEFAULT true,
    -- Уведомления о новых заявках (для админов)
    notify_new_orders BOOLEAN DEFAULT false,
    -- Минимальная схожесть для уведомлений (0-100%)
    min_match_percentage INT DEFAULT 70,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица для админов бота
CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.bot_admins (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL UNIQUE,
    username VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица для логирования отправленных уведомлений (чтобы не спамить)
CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.sent_notifications (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    order_id INT NOT NULL,
    notification_type VARCHAR(50) NOT NULL, -- 'matching_order', 'new_order'
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_notification_settings_chat_id 
ON t_p52349012_telegram_bot_creatio.notification_settings(chat_id);

CREATE INDEX IF NOT EXISTS idx_bot_admins_chat_id 
ON t_p52349012_telegram_bot_creatio.bot_admins(chat_id);

CREATE INDEX IF NOT EXISTS idx_sent_notifications_lookup 
ON t_p52349012_telegram_bot_creatio.sent_notifications(chat_id, order_id, notification_type);

-- Вставим первого админа (можно будет добавить позже через бота)
INSERT INTO t_p52349012_telegram_bot_creatio.bot_admins (chat_id, username, is_active)
VALUES (123456789, 'admin', true)
ON CONFLICT (chat_id) DO NOTHING;