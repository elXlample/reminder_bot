import logging
from datetime import datetime, timezone
from typing import Any

from .roles import UserRole
from psycopg import AsyncConnection

logger = logging.getLogger(__name__)


async def add_user(
    conn: AsyncConnection,
    *,
    user_id: int,
    username: str | None = None,
    language: str = "ru",
    role: UserRole = UserRole.USER,
    is_alive: bool = True,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO users(user_id, username, language, role, is_alive)
                VALUES(
                    %(user_id)s, 
                    %(username)s, 
                    %(language)s, 
                    %(role)s, 
                    %(is_alive)s 
                    
                ) ON CONFLICT DO NOTHING;
            """,
            params={
                "user_id": user_id,
                "username": username,
                "language": language,
                "role": role,
                "is_alive": is_alive,
            },
        )
    logger.info(
        "User added. Table=`%s`, user_id=%d, created_at='%s', "
        "language='%s', role=%s, is_alive=%s",
        "users",
        user_id,
        datetime.now(timezone.utc),
        language,
        role,
        is_alive,
    )


async def get_user(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> tuple[Any, ...] | None:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT 
                    id,
                    user_id,
                    username,
                    language,
                    role,
                    is_alive,
                    created_at
                    FROM users WHERE user_id = %s;
            """,
            params=(user_id,),
        )
        row = await data.fetchone()
    logger.info("Row is %s", row)
    return row if row else None


async def add_user_activity(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO activity (user_id)
                VALUES (%s)
                ON CONFLICT (user_id, activity_date)
                DO UPDATE
                SET actions = activity.actions + 1;
            """,
            params=(user_id,),
        )
    logger.info("User activity updated. table=`activity`, user_id=%d", user_id)


async def get_statistics(conn: AsyncConnection, user_id: int):
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT user_id, SUM(actions) AS total_actions
                FROM activity
                WHERE user_id = %s
                GROUP BY user_id;
            """,
            params=(user_id,),
        )
        rows = await data.fetchall()
    logger.info("Users activity got from table=`activity`")
    return [*rows] if rows else 0


async def change_user_alive_status(
    conn: AsyncConnection,
    *,
    is_alive: bool,
    user_id: int,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                UPDATE users
                SET is_alive = %s
                WHERE user_id = %s;
            """,
            params=(is_alive, user_id),
        )
    logger.info("Updated `is_alive` status to `%s` for user %d", is_alive, user_id)
