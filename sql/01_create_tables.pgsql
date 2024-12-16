CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_keys (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_secret TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (token_secret, user_id, session_id)
);

CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    likes_count BIGINT DEFAULT 0,
    dislikes_count BIGINT DEFAULT 0,
    comments_count BIGINT DEFAULT 0,
    tags TEXT[],
    media TEXT[],
    status VARCHAR(20) DEFAULT 'active',
    is_deleted BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_post_views (
    user_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, post_id),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comments (
    comment_id TEXT PRIMARY KEY,
    parent_comment_id TEXT,
    post_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    likes_count BIGINT DEFAULT 0,
    dislikes_count BIGINT DEFAULT 0,
    FOREIGN KEY (parent_comment_id) REFERENCES comments (comment_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reactions (
    post_id TEXT,
    comment_id TEXT,
    user_id TEXT NOT NULL,
    is_like BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (post_id, user_id),
    UNIQUE (comment_id, user_id),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE,
    FOREIGN KEY (comment_id) REFERENCES comments (comment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    banner_url TEXT,
    bio TEXT,
    gender TEXT,
    languages TEXT[],
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);