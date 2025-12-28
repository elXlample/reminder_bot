import logging
from datetime import datetime, timezone
from typing import Any
from config.config import Config, load_config
from .roles import UserRole
from psycopg import AsyncConnection

config: Config = load_config()

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=config.log.level,
    format=config.log.format,
)


async def add_todo(
    conn: AsyncConnection,
    *,
    user_id: int,
    username: str,
    todo: str,
    done: bool,
    reminder_time: datetime,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO todos (user_id,username,todo,done,reminder_time)
                VALUES (
                %(user_id)s,
                %(username)s,
                %(todo)s,
                %(done)s,
                %(reminder_time)s
                )
                ON CONFLICT DO NOTHING;
            """,
            params={
                "user_id": user_id,
                "username": username,
                "todo": todo,
                "done": done,
                "reminder_time": reminder_time,
            },
        )
    rowcount = cursor.rowcount
    if rowcount:
        logger.info("INSERTED DATA INTO TABLE TODOS")
    else:
        logger.warning("ERROR WHILE INSERTING INTO TODOS TABLE")
