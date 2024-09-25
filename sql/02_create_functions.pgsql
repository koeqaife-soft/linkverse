CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION delete_old_auth_keys()
RETURNS void AS $$
BEGIN
    DELETE FROM auth_keys
    WHERE created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- likes
CREATE OR REPLACE FUNCTION increment_likes_count() RETURNS TRIGGER AS $$
BEGIN
    UPDATE posts
    SET likes_count = likes_count + 1
    WHERE post_id = NEW.post_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION decrement_likes_count() RETURNS TRIGGER AS $$
BEGIN
    UPDATE posts
    SET likes_count = likes_count - 1
    WHERE post_id = OLD.post_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- comments
CREATE OR REPLACE FUNCTION increment_comments_count() RETURNS TRIGGER AS $$
BEGIN
    UPDATE posts
    SET comments_count = comments_count + 1
    WHERE post_id = NEW.post_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION decrement_comments_count() RETURNS TRIGGER AS $$
BEGIN
    UPDATE posts
    SET comments_count = comments_count - 1
    WHERE post_id = OLD.post_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
