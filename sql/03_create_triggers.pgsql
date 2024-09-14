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
