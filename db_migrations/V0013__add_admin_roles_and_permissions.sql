ALTER TABLE t_p52349012_telegram_bot_creatio.bot_admins 
ADD COLUMN IF NOT EXISTS role VARCHAR(50);

CREATE TABLE IF NOT EXISTS t_p52349012_telegram_bot_creatio.admin_permissions (
    id SERIAL PRIMARY KEY,
    admin_id INTEGER NOT NULL UNIQUE,
    can_view_stats BOOLEAN,
    can_view_orders BOOLEAN,
    can_remove_orders BOOLEAN,
    can_manage_users BOOLEAN,
    can_block_users BOOLEAN,
    can_manage_admins BOOLEAN,
    can_view_security_logs BOOLEAN,
    created_at TIMESTAMP
);

UPDATE t_p52349012_telegram_bot_creatio.bot_admins 
SET role = 'owner' 
WHERE id = 1;