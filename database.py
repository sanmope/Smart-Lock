from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Connection URL — SQLite saves everything in a local file
SQLALCHEMY_DATABASE_URL = "sqlite:///./smartlock.db"

# The engine is the connection to the DB
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # needed only for SQLite
)

# SessionLocal is the session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the class from which all your SQLAlchemy models will inherit
Base = declarative_base()

# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()