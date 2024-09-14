CREATE INDEX IF NOT EXISTS idx_user_id ON auth_keys(user_id);

CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts (user_id);
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts (created_at);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts (status);
CREATE INDEX IF NOT EXISTS idx_posts_is_deleted ON posts (is_deleted);
