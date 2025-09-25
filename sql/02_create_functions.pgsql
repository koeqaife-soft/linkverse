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

CREATE OR REPLACE FUNCTION update_deleted_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_deleted IS DISTINCT FROM OLD.is_deleted THEN
            NEW.deleted_at := CURRENT_TIMESTAMP;
        ELSE
            NEW.deleted_at := NULL;
        END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- (0) likes
-- (0) on insert
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

-- (0) on delete
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

-- (0) on update
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

-- (1) comments
-- (1) increment
    CREATE OR REPLACE FUNCTION increment_comments_count() RETURNS TRIGGER AS $$
    BEGIN
        UPDATE posts
        SET comments_count = comments_count + 1
        WHERE post_id = NEW.post_id;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

-- (1) decrement
    CREATE OR REPLACE FUNCTION decrement_comments_count() RETURNS TRIGGER AS $$
    BEGIN
        UPDATE posts
        SET comments_count = comments_count - 1
        WHERE post_id = OLD.post_id;
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;


-- (2) notification linked_type check
    CREATE OR REPLACE FUNCTION check_linked_id() RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.linked_type = 'comment' THEN
            IF NOT EXISTS (SELECT 1 FROM posts WHERE post_id = NEW.second_linked_id) THEN
                RAISE EXCEPTION 'Post with ID % does not exist', NEW.second_linked_id;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM comments WHERE comment_id = NEW.linked_id) THEN
                RAISE EXCEPTION 'Comment with ID % does not exist', NEW.linked_id;
            END IF;
        ELSIF NEW.linked_type = 'post' THEN
            IF NOT EXISTS (SELECT 1 FROM posts WHERE post_id = NEW.linked_id) THEN
                RAISE EXCEPTION 'Post with ID % does not exist', NEW.linked_id;
            END IF;
        ELSIF NEW.linked_type = 'mod_audit' THEN
            IF NOT EXISTS (SELECT 1 FROM mod_audit WHERE id = NEW.linked_id) THEN
                RAISE EXCEPTION 'Mod audit with ID % does not exist', NEW.linked_id;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

-- (3) auto delete linked resources
-- (3) comment
    CREATE OR REPLACE FUNCTION delete_resources_on_comment_delete() RETURNS TRIGGER AS $$
    BEGIN
        DELETE FROM user_notifications
        WHERE linked_type = 'comment' AND linked_id = OLD.comment_id;

        DELETE FROM reports
        WHERE target_type = 'comment' AND target_id = OLD.comment_id;

        DELETE FROM mod_assigned_resources
        WHERE resource_id = OLD.comment_id;

        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;

-- (3) post
    CREATE OR REPLACE FUNCTION delete_resources_on_post_delete() RETURNS TRIGGER AS $$
    BEGIN
        DELETE FROM user_notifications
        WHERE linked_type = 'post' AND linked_id = OLD.post_id;

        DELETE FROM reports
        WHERE target_type = 'post' AND target_id = OLD.post_id;

        DELETE FROM mod_assigned_resources
        WHERE resource_id = OLD.post_id;

        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;

-- (3) mod audit 
    CREATE OR REPLACE FUNCTION delete_resources_on_audit_delete() RETURNS TRIGGER AS $$
    BEGIN
        DELETE FROM user_notifications
        WHERE linked_type = 'mod_audit' AND linked_id = OLD.id;

        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;

-- (4) replies
-- (4) increment
    CREATE OR REPLACE FUNCTION increment_replies_count() RETURNS TRIGGER AS $$
    BEGIN
        UPDATE comments
        SET replies_count = replies_count + 1
        WHERE comment_id = NEW.parent_comment_id;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

-- (4) decrement
    CREATE OR REPLACE FUNCTION decrement_replies_count() 
    RETURNS TRIGGER AS $$
    DECLARE
        parent comments%ROWTYPE;
    BEGIN
        UPDATE comments
        SET replies_count = replies_count - 1
        WHERE comment_id = OLD.parent_comment_id
        RETURNING * INTO parent;

        IF parent.replies_count = 0
        AND parent.user_id IS NULL
        AND parent.content IS NULL THEN
            DELETE FROM comments WHERE comment_id = parent.comment_id;
        END IF;

        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;

-- (5) tag posts count
-- (5) increment
    CREATE OR REPLACE FUNCTION increment_tag_posts_count() RETURNS TRIGGER AS $$
    BEGIN
        UPDATE tags
        SET posts_count = posts_count + 1
        WHERE tag_id = NEW.tag_id;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

-- (5) decrement
    CREATE OR REPLACE FUNCTION decrement_tag_posts_count() RETURNS TRIGGER AS $$
    BEGIN
        UPDATE tags
        SET posts_count = posts_count - 1
        WHERE tag_id = OLD.tag_id;
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;


-- (6) File ref count
    CREATE OR REPLACE FUNCTION file_refcount_trigger()
    RETURNS TRIGGER AS $$
    DECLARE
        context_id_old TEXT;
        context_id_new TEXT;
    BEGIN
        EXECUTE format('SELECT ($1).%I', TG_ARGV[0])
        USING OLD INTO context_id_old;

        EXECUTE format('SELECT ($1).%I', TG_ARGV[0])
        USING NEW INTO context_id_new;

        -- decrement
        IF context_id_old IS NOT NULL
        AND (context_id_new IS NULL OR context_id_new IS DISTINCT FROM context_id_old) THEN
            UPDATE files
            SET reference_count = reference_count - 1
            WHERE context_id = context_id_old;
        END IF;

        -- increment
        IF context_id_new IS NOT NULL
        AND (context_id_old IS NULL OR context_id_new IS DISTINCT FROM context_id_old) THEN
            UPDATE files
            SET reference_count = reference_count + 1
            WHERE context_id = context_id_new;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

-- (7) followers
    CREATE OR REPLACE FUNCTION update_follow_counts()
    RETURNS TRIGGER AS $$
    BEGIN
        IF TG_OP = 'INSERT' THEN
            UPDATE users SET followers_count = followers_count + 1 
            WHERE user_id = NEW.followed_to;
            
            UPDATE users SET following_count = following_count + 1 
            WHERE user_id = NEW.user_id;
        ELSIF TG_OP = 'DELETE' THEN
            UPDATE users SET followers_count = followers_count - 1 
            WHERE user_id = OLD.followed_to;
            
            UPDATE users SET following_count = following_count - 1 
            WHERE user_id = OLD.user_id;
        END IF;
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;
