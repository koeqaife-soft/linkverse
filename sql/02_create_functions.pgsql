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
    IF NEW.is_like THEN
        UPDATE posts
        SET likes_count = likes_count + 1
        WHERE post_id = NEW.post_id;
    ELSE
        UPDATE posts
        SET dislikes_count = dislikes_count + 1
        WHERE post_id = NEW.post_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_likes_count_on_delete() RETURNS TRIGGER AS $$
BEGIN
    IF OLD.is_like THEN
        UPDATE posts
        SET likes_count = likes_count - 1
        WHERE post_id = OLD.post_id;
    ELSE
        UPDATE posts
        SET dislikes_count = dislikes_count - 1
        WHERE post_id = OLD.post_id;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_likes_count_on_update() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_like <> OLD.is_like THEN
        IF OLD.is_like THEN
            UPDATE posts
            SET likes_count = likes_count - 1
            WHERE post_id = OLD.post_id;
        ELSE
            UPDATE posts
            SET dislikes_count = dislikes_count - 1
            WHERE post_id = OLD.post_id;
        END IF;

        IF NEW.is_like THEN
            UPDATE posts
            SET likes_count = likes_count + 1
            WHERE post_id = NEW.post_id;
        ELSE
            UPDATE posts
            SET dislikes_count = dislikes_count + 1
            WHERE post_id = NEW.post_id;
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
