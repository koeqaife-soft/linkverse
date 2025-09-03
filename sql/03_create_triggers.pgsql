CREATE OR REPLACE TRIGGER update_posts_modified
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

-- (0) likes
-- (0) on insert
    CREATE OR REPLACE TRIGGER trigger_likes_insert
    AFTER INSERT ON reactions
    FOR EACH ROW
    EXECUTE FUNCTION update_likes_count_on_insert();

-- (0) on delete
    CREATE OR REPLACE TRIGGER trigger_likes_delete
    AFTER DELETE ON reactions
    FOR EACH ROW
    EXECUTE FUNCTION update_likes_count_on_delete();

-- (0) on update
    CREATE OR REPLACE TRIGGER trigger_likes_update
    AFTER UPDATE ON reactions
    FOR EACH ROW
    WHEN (OLD.is_like IS DISTINCT FROM NEW.is_like)
    EXECUTE FUNCTION update_likes_count_on_update();

-- (1) comments
-- (1) on insert
    CREATE OR REPLACE TRIGGER trigger_comments_insert
    AFTER INSERT ON comments
    FOR EACH ROW
    EXECUTE FUNCTION increment_comments_count();

-- (1) on delete
    CREATE OR REPLACE TRIGGER trigger_comments_delete
    AFTER DELETE ON comments
    FOR EACH ROW
    EXECUTE FUNCTION decrement_comments_count();

-- (2) notification linked_type check
    CREATE OR REPLACE TRIGGER trigger_check_linked_id
    BEFORE INSERT OR UPDATE ON user_notifications
    FOR EACH ROW EXECUTE FUNCTION check_linked_id();

-- (3) auto delete notification
-- (3) post
    CREATE OR REPLACE TRIGGER trigger_delete_notifications_on_comment_delete
    AFTER DELETE ON comments
    FOR EACH ROW EXECUTE FUNCTION delete_notifications_on_comment_delete();

-- (3) comment
    CREATE OR REPLACE TRIGGER trigger_delete_notifications_on_post_delete
    AFTER DELETE ON posts
    FOR EACH ROW EXECUTE FUNCTION delete_notifications_on_post_delete();

-- (4) replies
-- (4) on insert
    CREATE OR REPLACE TRIGGER trigger_replies_insert
    AFTER INSERT ON comments
    FOR EACH ROW
    WHEN (NEW.parent_comment_id IS NOT NULL)
    EXECUTE FUNCTION increment_replies_count();

-- (4) on delete
    CREATE OR REPLACE TRIGGER trigger_replies_delete
    AFTER DELETE ON comments
    FOR EACH ROW
    WHEN (OLD.parent_comment_id IS NOT NULL)
    EXECUTE FUNCTION decrement_replies_count();

-- (5) tag posts count
-- (5) increment
    CREATE OR REPLACE TRIGGER trigger_tag_posts_count_increment
    AFTER INSERT ON post_tags
    FOR EACH ROW
    EXECUTE FUNCTION increment_tag_posts_count();

-- (5) decrement
    CREATE OR REPLACE TRIGGER trigger_tag_posts_count_decrement
    AFTER DELETE ON post_tags
    FOR EACH ROW
    EXECUTE FUNCTION decrement_tag_posts_count();

-- (6) File ref count
-- (6)(posts) refcount
CREATE OR REPLACE TRIGGER posts_file_refcount
AFTER INSERT OR UPDATE OR DELETE ON posts
FOR EACH ROW
EXECUTE FUNCTION file_refcount_trigger('file_context_id');

-- (6)(user)(avatar) refcount
CREATE OR REPLACE TRIGGER user_avatar_file_refcount
AFTER INSERT OR UPDATE OR DELETE ON user_profiles
FOR EACH ROW
EXECUTE FUNCTION file_refcount_trigger('avatar_context_id');

-- (6)(user)(banner)
CREATE OR REPLACE TRIGGER user_banner_file_refcount
AFTER INSERT OR UPDATE OR DELETE ON user_profiles
FOR EACH ROW
EXECUTE FUNCTION file_refcount_trigger('banner_context_id');
