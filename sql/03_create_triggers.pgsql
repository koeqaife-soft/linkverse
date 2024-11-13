DO
$$BEGIN
    CREATE TRIGGER update_posts_modified
    BEFORE UPDATE ON posts
    FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.* AND
          (OLD.likes_count IS NOT DISTINCT FROM NEW.likes_count) AND
          (OLD.dislikes_count IS NOT DISTINCT FROM NEW.dislikes_count) AND
          (OLD.comments_count IS NOT DISTINCT FROM NEW.comments_count))
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
