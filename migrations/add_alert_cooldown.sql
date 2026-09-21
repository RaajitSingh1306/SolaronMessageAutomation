-- migrations/add_alert_cooldown.sql
-- Table to track operational status alert sends and prevent alerting the same customer repeatedly.

CREATE TABLE IF NOT EXISTS alert_send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    alert_type TEXT NOT NULL,          -- 'offline', 'fault', 'not_generating'
    severity TEXT NOT NULL,            -- 'warning', 'critical'
    sent_at DATETIME DEFAULT (datetime('now', 'utc')),
    channel TEXT DEFAULT 'whatsapp',   -- 'whatsapp', 'sms', 'email'
    platform_ref TEXT                  -- Gupshup/Freshworks message ID for tracking
);

CREATE INDEX IF NOT EXISTS idx_asl_plant_sent ON alert_send_log (plant_name, sent_at);
CREATE INDEX IF NOT EXISTS idx_asl_phone_sent ON alert_send_log (phone_number, sent_at);
