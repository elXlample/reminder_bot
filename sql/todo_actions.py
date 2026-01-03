from config.config import Config, load_config
import math
import logging
from datetime import datetime, timezone
from typing import Any
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
    user_timezone: str,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO todos (user_id,username,todo,done,reminder_time,timezone)
                VALUES (
                %(user_id)s,
                %(username)s,
                %(todo)s,
                %(done)s,
                %(reminder_time)s,
                %(timezone)s
                )
                ON CONFLICT DO NOTHING;
            """,
            params={
                "user_id": user_id,
                "username": username,
                "todo": todo,
                "done": done,
                "reminder_time": reminder_time,
                "timezone": user_timezone,
            },
        )
    rowcount = cursor.rowcount
    if rowcount:
        logger.info("INSERTED DATA INTO TABLE TODOS")
    else:
        logger.warning("ERROR WHILE INSERTING INTO TODOS TABLE")


async def get_todo_list(
    conn: AsyncConnection, *, user_id: int, page: int
) -> list[tuple[Any, ...]] | None:
    async with conn.cursor() as cursor:
        page_size = 10
        offset = (page - 1) * page_size
        data = await cursor.execute(
            query="""
                SELECT todo, reminder_time,done,timezone
                FROM todos
                WHERE user_id = %s
                ORDER BY reminder_time
                LIMIT %s OFFSET %s
            """,
            params=(user_id, page_size, offset),
        )

        row = await data.fetchall()
    logger.info("Row is %s", row)
    return row if row else None


async def get_total_pages(conn: AsyncConnection, *, user_id: int) -> int | None:
    async with conn.cursor() as cursor:
        page_size = 10

        await cursor.execute(
            query="""
            SELECT COUNT(*) FROM todos WHERE user_id = %s
            """,
            params=(user_id,),
        )
        total_count = (await cursor.fetchone())[0]

        return max(1, math.ceil(total_count / page_size))


async def get_all_todos(conn: AsyncConnection) -> list[tuple[Any, ...]] | None:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT user_id, todo, reminder_time, done, timezone
                FROM todos;
                
            """,
        )
        row = await data.fetchall()
    logger.info("Row is %s", row)
    return row if row else None


async def change_todo_status(
    conn: AsyncConnection, *, boolean: bool, user_id: int, todo: str
) -> None:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                UPDATE todos
                SET done = %s
                WHERE user_id = %s AND todo = %s

            """,
            params=(boolean, user_id, todo),
        )
        rowcount = cursor.rowcount
        logger.info(f"{rowcount} while updating todos")


async def remove_todo(conn: AsyncConnection, *, user_id: int, todo: str) -> None:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                DELETE FROM todos
                WHERE user_id = %s AND todo = %s

            """,
            params=(user_id, todo),
        )

        rowcount = cursor.rowcount
        logger.info(f"{rowcount} while updating todos")
