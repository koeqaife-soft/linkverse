CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    avatar_url TEXT
);

CREATE TABLE IF NOT EXISTS auth_keys (
    user_id BIGINT NOT NULL,
    token_secret TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (token_secret, user_id)
);

CREATE TABLE IF NOT EXISTS posts (
    post_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    likes_count INT DEFAULT 0,
    comments_count INT DEFAULT 0,
    tags TEXT[],
    media TEXT[],
    status VARCHAR(20) DEFAULT 'active',
    is_deleted BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS likes (
    post_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE,
    UNIQUE (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS comments (
    post_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE,
    UNIQUE (post_id, user_id)
);
