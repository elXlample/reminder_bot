from environs import Env
from dataclasses import dataclass
import os
import logging

logger = logging.getLogger(__name__)

# for non-server


# LOG_LEVEL = "INFO"
# LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class DatabaseSettings:
    name: str
    host: str
    port: int
    user: str
    password: str


@dataclass
class BotSet:
    token: str
    admin_id: int


@dataclass
class LoggerSet:
    level: str
    format: str


@dataclass
class RedisSettings:
    host: str
    port: int
    db: int
    password: str
    username: str


@dataclass
class Config:
    bot: BotSet
    db: DatabaseSettings
    redis: RedisSettings
    log: LoggerSet


@dataclass
class RedisSettings:
    host: str
    port: int
    db: int
    password: str
    username: str


def load_env(path: str | None = None):
    env = Env()
    env.read_env(path or ".env")
    return env


def load_config(path: str | None = None) -> Config:
    env = load_env()
    token = env("BOT_TOKEN")
    admin_id = env("ADMIN_ID")
    db = DatabaseSettings(
        name=env("POSTGRES_DB"),
        host=env("POSTGRES_HOST"),
        port=env.int("POSTGRES_PORT"),
        user=env("POSTGRES_USER"),
        password=env("POSTGRES_PASSWORD"),
    )

    redis = RedisSettings(
        host=env("REDIS_HOST"),
        port=env.int("REDIS_PORT"),
        db=env.int("REDIS_DATABASE"),
        password=env("REDIS_PASSWORD", default=""),
        username=env("REDIS_USERNAME", default=""),
    )

    logg_settings = LoggerSet(level=env("LOG_LEVEL"), format=env("LOG_FORMAT"))

    logger.info("Configuration loaded successfully")

    return Config(
        bot=BotSet(token=token, admin_id=admin_id),
        db=db,
        redis=redis,
        log=logg_settings,
    )
