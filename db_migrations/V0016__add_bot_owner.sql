-- Добавление владельца бота
INSERT INTO t_p52349012_telegram_bot_creatio.bot_admins (chat_id, username, is_active, role) 
VALUES (352891390, 'owner', true, 'owner')
ON CONFLICT (chat_id) DO UPDATE 
SET is_active = true, role = 'owner';