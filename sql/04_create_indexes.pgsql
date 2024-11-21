CREATE INDEX IF NOT EXISTS idx_auth_keys ON auth_keys(user_id, token_secret);

CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts (user_id);
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts (created_at);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts (status);
CREATE INDEX IF NOT EXISTS idx_posts_is_deleted ON posts (is_deleted);

CREATE INDEX IF NOT EXISTS idx_reactions_user_id ON reactions (user_id);
CREATE INDEX IF NOT EXISTS idx_reactions_post_id ON reactions (post_id);
CREATE INDEX IF NOT EXISTS idx_reactions_comment_id ON reactions (comment_id);

CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments (user_id);
CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments (post_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON comments (parent_comment_id);
