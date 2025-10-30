CREATE OR REPLACE VIEW user_channel_view AS
SELECT
    uc.user_id,
    uc.channel_id,
    uc.membership_id,
    uc.last_read_message_id,
    uc.last_read_at,
    cm.joined_at,
    c.metadata,
    c.type,
    c.created_at,
    COALESCE(
        array_agg(cm2.user_id)
        FILTER (WHERE cm2.user_id IS NOT NULL),
        '{{}}'
    ) AS members
FROM user_channels uc
LEFT JOIN channel_members cm ON cm.membership_id = uc.membership_id
LEFT JOIN channels c ON c.channel_id = uc.channel_id
LEFT JOIN channel_members cm2 ON cm2.channel_id = c.channel_id
GROUP BY cm.membership_id, uc.membership_id, c.channel_id, cm2.channel_id;

