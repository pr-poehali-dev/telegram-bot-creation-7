ALTER TABLE t_p52349012_telegram_bot_creatio.sender_orders 
ADD COLUMN IF NOT EXISTS marketplace VARCHAR(100);

ALTER TABLE t_p52349012_telegram_bot_creatio.carrier_orders 
ADD COLUMN IF NOT EXISTS marketplace VARCHAR(100);

CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.user_subscriptions (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_type VARCHAR(20) NOT NULL,
    subscription_type VARCHAR(20) NOT NULL,
    warehouse_filter TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);