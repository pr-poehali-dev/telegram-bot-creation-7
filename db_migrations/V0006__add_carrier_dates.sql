ALTER TABLE t_p52349012_telegram_bot_creatio.carrier_orders 
ADD COLUMN IF NOT EXISTS loading_date DATE,
ADD COLUMN IF NOT EXISTS arrival_date DATE;

CREATE INDEX IF NOT EXISTS idx_carrier_orders_loading_date 
ON t_p52349012_telegram_bot_creatio.carrier_orders(loading_date);

CREATE INDEX IF NOT EXISTS idx_carrier_orders_arrival_date 
ON t_p52349012_telegram_bot_creatio.carrier_orders(arrival_date);