ALTER TABLE t_p52349012_telegram_bot_creatio.sender_orders 
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE t_p52349012_telegram_bot_creatio.carrier_orders 
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_sender_orders_created_at 
ON t_p52349012_telegram_bot_creatio.sender_orders(created_at);

CREATE INDEX IF NOT EXISTS idx_carrier_orders_created_at 
ON t_p52349012_telegram_bot_creatio.carrier_orders(created_at);