DO
$$BEGIN
    CREATE TRIGGER update_posts_modified
    BEFORE UPDATE ON posts
    FOR EACH ROW
    WHEN (
        (OLD.user_id IS DISTINCT FROM NEW.user_id OR
         OLD.content IS DISTINCT FROM NEW.content OR
         OLD.created_at IS DISTINCT FROM NEW.created_at OR
         OLD.updated_at IS DISTINCT FROM NEW.updated_at OR
         OLD.likes_count IS DISTINCT FROM NEW.likes_count OR
         OLD.dislikes_count IS DISTINCT FROM NEW.dislikes_count OR
         OLD.comments_count IS DISTINCT FROM NEW.comments_count OR
         OLD.tags IS DISTINCT FROM NEW.tags OR
         OLD.media IS DISTINCT FROM NEW.media OR
         OLD.status IS DISTINCT FROM NEW.status OR
         OLD.is_deleted IS DISTINCT FROM NEW.is_deleted)
        AND (OLD.likes_count IS NOT DISTINCT FROM NEW.likes_count)
        AND (OLD.dislikes_count IS NOT DISTINCT FROM NEW.dislikes_count)
        AND (OLD.comments_count IS NOT DISTINCT FROM NEW.comments_count)
    )
    EXECUTE FUNCTION update_modified_column();
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END;$$;

-- likes
DO
$$BEGIN
    CREATE TRIGGER trigger_likes_insert
    AFTER INSERT ON reactions
    FOR EACH ROW
    EXECUTE FUNCTION update_likes_count_on_insert();

    CREATE TRIGGER trigger_likes_delete
    AFTER DELETE ON reactions
    FOR EACH ROW
    EXECUTE FUNCTION update_likes_count_on_delete();

    CREATE TRIGGER trigger_likes_update
    AFTER UPDATE ON reactions
    FOR EACH ROW
    WHEN (OLD.is_like IS DISTINCT FROM NEW.is_like)
    EXECUTE FUNCTION update_likes_count_on_update();

EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END;$$;

-- comments
DO
$$BEGIN
    CREATE TRIGGER trigger_comments_insert
    AFTER INSERT ON comments
    FOR EACH ROW
    EXECUTE FUNCTION increment_comments_count();

    CREATE TRIGGER trigger_comments_delete
    AFTER DELETE ON comments
    FOR EACH ROW
    EXECUTE FUNCTION decrement_comments_count();
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END;$$;
