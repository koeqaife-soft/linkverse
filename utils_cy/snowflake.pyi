class SnowflakeGeneration:
    def __init__(
        self, server_id: int = 1, pid: int | None = None
    ) -> None:
        ...

    def generate(self) -> int:
        ...

    def parse(self, snowflake_id: int | str) -> tuple[float, int, int, int]:
        ...
