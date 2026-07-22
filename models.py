"""
SQLAlchemy Database Model
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum as SQLEnum, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
import enum
import os

Base = declarative_base()


class ImageStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ImagePost(Base):
    """Image record table"""
    __tablename__ = "image_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False, comment="Original filename")
    filepath = Column(String(512), nullable=False, comment="Storage path")
    status = Column(SQLEnum(ImageStatus), default=ImageStatus.PENDING, nullable=False, comment="Review status")
    ai_score = Column(Float, nullable=True, comment="AI review confidence 0-100")
    ai_tags = Column(String(512), nullable=True, comment="AI detected tags")
    reject_reason = Column(String(255), nullable=True, comment="Rejection reason")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# Database initialization
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./images.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)