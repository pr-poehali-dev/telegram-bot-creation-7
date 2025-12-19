-- Создание таблицы шаблонов заявок
CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.order_templates (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    template_name VARCHAR(100) NOT NULL,
    order_type VARCHAR(20) NOT NULL CHECK (order_type IN ('sender', 'carrier')),
    template_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, template_name)
);

CREATE INDEX idx_templates_chat_id ON t_p52349012_telegram_bot_creatio.order_templates(chat_id);