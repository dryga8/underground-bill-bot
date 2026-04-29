-- Пользователи
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Активности
CREATE TABLE activities (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    activity_type TEXT NOT NULL CHECK (activity_type IN ('steps', 'exercise')),
    activity_date DATE NOT NULL,
    month INTEGER NOT NULL,
    year INTEGER NOT NULL,
    steps_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, activity_type, activity_date)
);

-- XP пользователей
CREATE TABLE IF NOT EXISTS xp (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
    total_xp INTEGER DEFAULT 0
);

-- Всего шагов за всё время
CREATE TABLE IF NOT EXISTS total_steps (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
    all_time_steps BIGINT DEFAULT 0
);

-- Карцер
CREATE TABLE jails (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    activity_type TEXT NOT NULL DEFAULT 'steps',
    jailed_at TIMESTAMPTZ DEFAULT NOW(),
    jailed_until DATE NOT NULL,
    active BOOLEAN DEFAULT TRUE
);

-- Миграции для существующих таблиц
ALTER TABLE jails ADD COLUMN IF NOT EXISTS activity_type TEXT DEFAULT 'steps';
ALTER TABLE activities ADD COLUMN IF NOT EXISTS steps_count INTEGER DEFAULT 0;
CREATE TABLE IF NOT EXISTS xp (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
    total_xp INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS total_steps (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
    all_time_steps BIGINT DEFAULT 0
);

-- Жалобы
CREATE TABLE reports (
    id BIGSERIAL PRIMARY KEY,
    reporter_id BIGINT REFERENCES users(user_id),
    reported_user_id BIGINT REFERENCES users(user_id),
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    vote_message_id BIGINT,
    thread_id INTEGER,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'jailed', 'cleared')),
    yes_votes INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Голоса
CREATE TABLE report_votes (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT REFERENCES reports(id),
    voter_id BIGINT REFERENCES users(user_id),
    voted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(report_id, voter_id)
);

-- Админы
CREATE TABLE admins (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
    added_by BIGINT,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

-- Награды за уровни
CREATE TABLE IF NOT EXISTS rewards (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    level INTEGER NOT NULL,
    reward TEXT NOT NULL,
    awarded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_activities_user_month ON activities(user_id, month, year);
CREATE INDEX idx_jails_active ON jails(user_id, active);
CREATE INDEX idx_reports_status ON reports(status);
