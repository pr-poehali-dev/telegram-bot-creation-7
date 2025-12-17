-- Обновление структуры таблицы sender_orders
ALTER TABLE sender_orders 
  RENAME COLUMN pickup_address TO loading_address;

ALTER TABLE sender_orders 
  ADD COLUMN IF NOT EXISTS loading_date DATE,
  ADD COLUMN IF NOT EXISTS loading_time TIME,
  ADD COLUMN IF NOT EXISTS pallet_quantity INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS box_quantity INTEGER DEFAULT 0;

-- Обновление структуры таблицы carrier_orders
ALTER TABLE carrier_orders 
  ADD COLUMN IF NOT EXISTS pallet_capacity INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS box_capacity INTEGER DEFAULT 0;