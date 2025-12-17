-- Таблица для управления индивидуальными лимитами пользователей
CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.user_limits (
    chat_id BIGINT PRIMARY KEY,
    daily_order_limit INT DEFAULT 10,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица для логирования подозрительных действий
CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.security_logs (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    details TEXT,
    severity VARCHAR(20) DEFAULT 'medium',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица для автоматической блокировки
CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.auto_blocked_users (
    chat_id BIGINT PRIMARY KEY,
    reason TEXT NOT NULL,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_reviewed BOOLEAN DEFAULT FALSE,
    reviewed_by_admin BOOLEAN DEFAULT FALSE
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_security_logs_chat_id ON t_p52349012_telegram_bot_creatio.security_logs(chat_id);
CREATE INDEX IF NOT EXISTS idx_security_logs_created_at ON t_p52349012_telegram_bot_creatio.security_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_security_logs_severity ON t_p52349012_telegram_bot_creatio.security_logs(severity);
CREATE INDEX IF NOT EXISTS idx_auto_blocked_reviewed ON t_p52349012_telegram_bot_creatio.auto_blocked_users(is_reviewed);
