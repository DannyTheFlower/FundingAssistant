from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_URL: str = f"sqlite:///{Path(__file__).resolve().parent.parent / 'db.sqlite3'}"

    class Config:
        env_file = ".env"


settings = Settings()
