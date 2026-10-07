# import sqlite3

# DATABASE_NAME = "tasks.db"


# def get_connection():
#     connection = sqlite3.connect(
#         DATABASE_NAME,
#         check_same_thread=False
#     )

#     connection.row_factory = sqlite3.Row

#     return connection


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./tasks.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
