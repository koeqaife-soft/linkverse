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
CREATE OR REPLACE FUNCTION update_likes_count_on_insert() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.comment_id IS NULL THEN
        UPDATE posts
        SET likes_count = likes_count + CASE WHEN NEW.is_like THEN 1 ELSE 0 END,
            dislikes_count = dislikes_count + CASE WHEN NOT NEW.is_like THEN 1 ELSE 0 END
        WHERE post_id = NEW.post_id;
    ELSE
        UPDATE comments
        SET likes_count = likes_count + CASE WHEN NEW.is_like THEN 1 ELSE 0 END,
            dislikes_count = dislikes_count + CASE WHEN NOT NEW.is_like THEN 1 ELSE 0 END
        WHERE comment_id = NEW.comment_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_likes_count_on_delete() RETURNS TRIGGER AS $$
BEGIN
    IF OLD.comment_id IS NULL THEN
        UPDATE posts
        SET likes_count = likes_count - CASE WHEN OLD.is_like THEN 1 ELSE 0 END,
            dislikes_count = dislikes_count - CASE WHEN NOT OLD.is_like THEN 1 ELSE 0 END
        WHERE post_id = OLD.post_id;
    ELSE
        UPDATE comments
        SET likes_count = likes_count - CASE WHEN OLD.is_like THEN 1 ELSE 0 END,
            dislikes_count = dislikes_count - CASE WHEN NOT OLD.is_like THEN 1 ELSE 0 END
        WHERE comment_id = OLD.comment_id;
    END IF;

    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_likes_count_on_update() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.comment_id IS NULL THEN
        IF NEW.is_like <> OLD.is_like THEN
            UPDATE posts
            SET likes_count = likes_count + CASE WHEN NEW.is_like THEN 1 ELSE -1 END,
                dislikes_count = dislikes_count + CASE WHEN NOT NEW.is_like THEN 1 ELSE -1 END
            WHERE post_id = NEW.post_id;
        END IF;
    ELSE
        IF NEW.is_like <> OLD.is_like THEN
            UPDATE comments
            SET likes_count = likes_count + CASE WHEN NEW.is_like THEN 1 ELSE -1 END,
                dislikes_count = dislikes_count + CASE WHEN NOT NEW.is_like THEN 1 ELSE -1 END
            WHERE comment_id = NEW.comment_id;
        END IF;
    END IF;

    RETURN NEW;
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
