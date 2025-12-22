from dataclasses import dataclass
import os

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


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


# def load_env(path: str | None = None):
#  env = Env()
#  env.read_env(path or ".env")
#   return env


def load_config(path: str | None = None) -> Config:
    # env = load_env()
    return Config(
        bot=Bot(token=os.getenv("BOT_TOKEN")),
        logger=Logger(level=LOG_LEVEL, format=LOG_FORMAT),
    )
