CREATE INDEX IF NOT EXISTS idx_auth_keys_session ON auth_keys(user_id, token_secret, session_id);
CREATE INDEX IF NOT EXISTS idx_auth_keys ON auth_keys(user_id, token_secret);

CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts (user_id);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts (status);
CREATE INDEX IF NOT EXISTS idx_posts_is_deleted ON posts (is_deleted);
CREATE INDEX IF NOT EXISTS idx_posts_popularity ON posts (popularity_score DESC);

CREATE INDEX IF NOT EXISTS idx_reactions_user_id_is_like ON reactions (user_id, is_like);
CREATE INDEX IF NOT EXISTS idx_reactions_user_id ON reactions (user_id);

CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments (user_id);
CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments (post_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON comments (parent_comment_id);
CREATE INDEX IF NOT EXISTS idx_comments_type ON comments (type);

CREATE INDEX IF NOT EXISTS users_id_num_idx ON users ((user_id::bigint));
CREATE INDEX IF NOT EXISTS profiles_id_num_idx ON user_profiles ((user_id::bigint));
CREATE INDEX IF NOT EXISTS notifications_id_num_idx ON user_notifications ((id::bigint));
CREATE INDEX IF NOT EXISTS posts_id_num_idx ON posts ((post_id::bigint));
CREATE INDEX IF NOT EXISTS comments_id_num_idx ON comments ((comment_id::bigint));
CREATE INDEX IF NOT EXISTS tag_id_num_idx ON tags ((tag_id::bigint));

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON user_notifications (user_id, unread);
