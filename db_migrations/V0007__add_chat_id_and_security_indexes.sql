-- Добавление колонки chat_id для отслеживания владельцев заявок

ALTER TABLE t_p52349012_telegram_bot_creatio.sender_orders 
ADD COLUMN IF NOT EXISTS chat_id BIGINT;

ALTER TABLE t_p52349012_telegram_bot_creatio.carrier_orders 
ADD COLUMN IF NOT EXISTS chat_id BIGINT;

-- Создание индексов для быстрого поиска заявок пользователя
CREATE INDEX IF NOT EXISTS idx_sender_orders_chat_id 
ON t_p52349012_telegram_bot_creatio.sender_orders(chat_id);

CREATE INDEX IF NOT EXISTS idx_carrier_orders_chat_id 
ON t_p52349012_telegram_bot_creatio.carrier_orders(chat_id);

-- Создание индексов для подсчета заявок за день (для rate limiting)
CREATE INDEX IF NOT EXISTS idx_sender_orders_created_at 
ON t_p52349012_telegram_bot_creatio.sender_orders(created_at);

CREATE INDEX IF NOT EXISTS idx_carrier_orders_created_at 
ON t_p52349012_telegram_bot_creatio.carrier_orders(created_at);
