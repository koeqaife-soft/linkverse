DO
$$BEGIN
    CREATE TRIGGER update_posts_modified
    BEFORE UPDATE ON posts
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END;$$;

-- likes
DO
$$BEGIN
    CREATE TRIGGER trigger_likes_insert
    AFTER INSERT ON likes
    FOR EACH ROW
    EXECUTE FUNCTION increment_likes_count();

    CREATE TRIGGER trigger_likes_delete
    AFTER DELETE ON likes
    FOR EACH ROW
    EXECUTE FUNCTION decrement_likes_count();
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
