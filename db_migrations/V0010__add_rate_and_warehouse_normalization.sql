-- Add rate column to sender_orders table
ALTER TABLE t_p52349012_telegram_bot_creatio.sender_orders 
ADD COLUMN IF NOT EXISTS rate INTEGER;

-- Add warehouse_normalized column for fuzzy matching
ALTER TABLE t_p52349012_telegram_bot_creatio.sender_orders 
ADD COLUMN IF NOT EXISTS warehouse_normalized VARCHAR(255);

ALTER TABLE t_p52349012_telegram_bot_creatio.carrier_orders 
ADD COLUMN IF NOT EXISTS warehouse_normalized VARCHAR(255);

-- Create index for faster warehouse matching
CREATE INDEX IF NOT EXISTS idx_sender_warehouse_normalized 
ON t_p52349012_telegram_bot_creatio.sender_orders(warehouse_normalized);

CREATE INDEX IF NOT EXISTS idx_carrier_warehouse_normalized 
ON t_p52349012_telegram_bot_creatio.carrier_orders(warehouse_normalized);