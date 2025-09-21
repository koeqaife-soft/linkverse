CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role_id INT DEFAULT 0,
    followers_count BIGINT NOT NULL DEFAULT 0,
    following_count BIGINT NOT NULL DEFAULT 0
);


CREATE TABLE IF NOT EXISTS user_notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    message TEXT,
    from_id TEXT NOT NULL,
    linked_type TEXT,
    linked_id TEXT,
    second_linked_id TEXT,
    unread BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (from_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_keys (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_secret TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (token_secret, user_id, session_id)
);

CREATE TABLE IF NOT EXISTS files (
    context_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    objects TEXT[] NOT NULL,
    reference_count INT NOT NULL DEFAULT 0,
    allowed_count INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    type TEXT NOT NULL DEFAULT 'context',  -- "avatar" | "banner" | "post_video" | "post_image" | any
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ DEFAULT NULL,
    likes_count BIGINT DEFAULT 0,
    dislikes_count BIGINT DEFAULT 0,
    comments_count BIGINT DEFAULT 0,
    popularity_score BIGINT GENERATED ALWAYS AS (likes_count - dislikes_count + (comments_count * 0.25)) STORED,
    tags TEXT[],
    file_context_id TEXT,
    status VARCHAR(20) DEFAULT 'active',
    is_deleted BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (file_context_id) REFERENCES files(context_id)
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
    user_id TEXT,
    content TEXT,
    likes_count BIGINT DEFAULT 0,
    dislikes_count BIGINT DEFAULT 0,
    replies_count BIGINT DEFAULT 0,
    popularity_score BIGINT GENERATED ALWAYS AS (likes_count - dislikes_count + (replies_count * 0.25)) STORED,
    type TEXT DEFAULT 'comment',
    FOREIGN KEY (parent_comment_id) REFERENCES comments (comment_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reactions (
    post_id TEXT NOT NULL,
    comment_id TEXT,
    user_id TEXT NOT NULL,
    is_like BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (post_id, comment_id, user_id),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE,
    FOREIGN KEY (comment_id) REFERENCES comments (comment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    comment_id TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (post_id, comment_id, user_id),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE,
    FOREIGN KEY (comment_id) REFERENCES comments (comment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS followed (
    user_id TEXT NOT NULL,
    followed_to TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, followed_to),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (followed_to) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT,
    banner_context_id TEXT,
    avatar_context_id TEXT,
    bio TEXT,
    languages TEXT[],
    badges SMALLINT[],
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (banner_context_id) REFERENCES files(context_id),
    FOREIGN KEY (avatar_context_id) REFERENCES files(context_id)

);

CREATE TABLE IF NOT EXISTS tags (
    tag_id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    posts_count BIGINT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS post_tags (
    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, tag_id)
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL
        CHECK (target_type IN ('post', 'comment', 'user', 'message')),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS webpush_subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    expiration_time TIMESTAMPTZ,
    raw JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (session_id),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES auth_keys (session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mod_audit (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    towards_to TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB,
    old_content JSONB,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    role_id TEXT NOT NULL,
    appellation_status TEXT NOT NULL DEFAULT 'none'
        CHECK (appellation_status IN ('none', 'pending', 'rejected', 'approved'))
);

CREATE TABLE IF NOT EXISTS mod_assigned_resources (
    resource_id TEXT NOT NULL,
    resource_type TEXT NOT NULL
        CHECK (resource_type IN ('post', 'comment', 'user', 'message', 'appellation')),
    assigned_to TEXT NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (resource_id, resource_type),
    FOREIGN KEY (assigned_to) REFERENCES users (user_id) ON DELETE CASCADE
);

