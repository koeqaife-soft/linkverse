from dataclasses import dataclass, asdict
from utils.generation import parse_id
from core import Status
from _types import connection_type


@dataclass
class User:
    user_id: int
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None
    bio: str | None = None
    gender: str | None = None
    languages: list[str] | None = None

    @property
    def created_at(self):
        try:
            return self._created_at
        except AttributeError:
            self._created_at = int(parse_id(self.user_id)[0])
            return self._created_at

    @property
    def dict(self) -> dict:
        _dict = asdict(self)
        _dict["created_at"] = self.created_at
        return _dict

    def __dict__(self):
        return self.dict


async def get_user(
    user_id: int, db: connection_type
) -> Status[User | None]:
    query = """
        SELECT u.user_id, u.username, p.display_name, p.avatar_url,
               p.banner_url, p.bio, p.gender, p.languages
        FROM users u
        LEFT JOIN user_profiles p ON u.user_id = p.user_id
        WHERE u.user_id = $1;
    """
    row = await db.fetchrow(query, user_id)

    if row is None:
        return Status(False, message="USER_DOES_NOT_EXIST")

    return Status(True, data=User(**dict(row)))


async def update_user(
    user_id: int, values: dict[str, str],
    db: connection_type
) -> Status[None]:
    allowed_values = {"display_name", "avatar_url", "banner_url",
                      "bio", "gender", "languages"}

    new_values = {
        k: v for k, v in values.items()
        if k in allowed_values and v is not None
    }

    if not new_values:
        return Status(False, message="NO_DATA")

    columns = ', '.join(new_values.keys())
    placeholders = ', '.join(f'${i+2}' for i in range(len(new_values)))
    update_clause = ', '.join(f"{k} = EXCLUDED.{k}" for k in new_values)

    query = f"""
        INSERT INTO user_profiles (user_id, {columns})
        VALUES ($1, {placeholders})
        ON CONFLICT (user_id)
        DO UPDATE SET {update_clause}
    """
    async with db.transaction():
        await db.execute(
            query, user_id, *new_values.values()
        )
    return Status(True)


async def change_username(
    user_id: int, username: str,
    db: connection_type
) -> Status[None]:
    async with db.transaction():
        await db.execute(
            """
            UPDATE users
            SET username = $1
            WHERE user_id = $2
            """, username, user_id
        )
    return Status(True)
