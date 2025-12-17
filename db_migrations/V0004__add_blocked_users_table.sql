CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.blocked_users (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL UNIQUE,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blocked_users_chat_id ON t_p52349012_telegram_bot_creatio.blocked_users(chat_id);