from utils.cache import auth as cache_auth
import utils.auth as auth
from utils.database import AutoConnection
from realtime.base import WebSocketState
from core import FunctionError
from state import pool


async def ws_token(
    token: str,
    state: WebSocketState,
    use_cache: bool = True
) -> bool:
    result: dict = {}
    try:
        async with AutoConnection(pool) as conn:
            if use_cache:
                callback = cache_auth.check_token
            else:
                callback = auth.check_token
            result = await callback(token, conn)
    except FunctionError:
        return False

    state.token = token
    state.token_result = result
    state.user_id = result["user_id"]
    state.session_id = result["session_id"]
    return True
