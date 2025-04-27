from sqlmodel import SQLModel, create_engine
from config import settings


engine = create_engine(settings.DB_URL, echo=False, connect_args={"check_same_thread": False})


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
