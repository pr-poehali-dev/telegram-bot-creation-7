-- Add loading_city field to sender_orders and carrier_orders tables

ALTER TABLE t_p52349012_telegram_bot_creatio.sender_orders 
ADD COLUMN IF NOT EXISTS loading_city VARCHAR(255);

ALTER TABLE t_p52349012_telegram_bot_creatio.carrier_orders 
ADD COLUMN IF NOT EXISTS loading_city VARCHAR(255);

-- Add normalized version for matching
ALTER TABLE t_p52349012_telegram_bot_creatio.sender_orders 
ADD COLUMN IF NOT EXISTS loading_city_normalized VARCHAR(255);

ALTER TABLE t_p52349012_telegram_bot_creatio.carrier_orders 
ADD COLUMN IF NOT EXISTS loading_city_normalized VARCHAR(255);

-- Create index for faster search
CREATE INDEX IF NOT EXISTS idx_sender_orders_loading_city_normalized 
ON t_p52349012_telegram_bot_creatio.sender_orders(loading_city_normalized);

CREATE INDEX IF NOT EXISTS idx_carrier_orders_loading_city_normalized 
ON t_p52349012_telegram_bot_creatio.carrier_orders(loading_city_normalized);