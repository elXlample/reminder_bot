from dataclasses import dataclass
from environs import Env
import os


@dataclass
class Bot:
    token: str


@dataclass
class Logger:
    level: str
    format: str


@dataclass
class Config:
    bot: Bot
    logger: Logger


def load_env(path: str | None = None):
    env = Env()
    env.read_env(path or ".env")
    return env


def load_config(path: str | None = None) -> Config:
    env = load_env()
    return Config(
        bot=Bot(token=os.getenv("BOT_TOKEN")),
        logger=Logger(level=env("LOG_LEVEL"), format=env("LOG_FORMAT")),
    )
