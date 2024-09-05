import time
import enum

created = 0
MAX_CREATED = 10000


class Action(enum.IntFlag):
    DEFAULT = 1
    CREATE_USER = 2
    CREATE_MESSAGE = 3
    CREATE_POST = 4
    SESSION = 5


def generate_id(action_id: Action = Action.DEFAULT) -> int:
    global created
    created = (created + 1) % MAX_CREATED

    timestamp_ms = int(time.time() * 1000)
    numeric_id = (timestamp_ms * MAX_CREATED + created) * 100 + int(action_id)

    return numeric_id
