local now = tonumber(ARGV[1])

if not now then
  return {'ERR', 'missing_now'}
end

local n = #KEYS
local offset = 2

for i = 1, n do
  local argbase = offset + (i - 1) * 3
  local limit = tonumber(ARGV[argbase])
  local window = tonumber(ARGV[argbase + 1])

  if not limit or not window then
    return {'ERR', 'bad_args'}
  end

  redis.call('ZREMRANGEBYSCORE', KEYS[i], 0, now - window)
  local count = redis.call('ZCARD', KEYS[i])

  if count >= limit then
    local oldest = redis.call('ZRANGE', KEYS[i], 0, 0, 'WITHSCORES')
    local reset
    if oldest[2] then
      reset = tonumber(oldest[2]) + window
    else
      reset = now + window
    end
    return {'RATE_LIMIT', KEYS[i], tostring(limit), tostring(reset)}
  end
end

for i = 1, n do
  local argbase = offset + (i - 1) * 3
  local window = tonumber(ARGV[argbase + 1])
  local member = ARGV[argbase + 2]
  redis.call('ZADD', KEYS[i], now, member)
  redis.call('EXPIRE', KEYS[i], window)
end

return {'OK'}
