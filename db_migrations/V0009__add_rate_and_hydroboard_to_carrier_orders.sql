-- Добавление полей rate (ставка в рублях) и hydroboard (гидроборт) в таблицу carrier_orders
ALTER TABLE t_p52349012_telegram_bot_creatio.carrier_orders 
ADD COLUMN IF NOT EXISTS rate INTEGER,
ADD COLUMN IF NOT EXISTS hydroboard VARCHAR(10);