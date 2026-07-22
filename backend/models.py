"""
SQLAlchemy 数据库模型
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
    """图片记录表"""
    __tablename__ = "image_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False, comment="原始文件名")
    filepath = Column(String(512), nullable=False, comment="存储路径")
    status = Column(SQLEnum(ImageStatus), default=ImageStatus.PENDING, nullable=False, comment="审核状态")
    ai_score = Column(Float, nullable=True, comment="AI 审核置信度 0-100")
    ai_tags = Column(String(512), nullable=True, comment="AI 识别标签")
    reject_reason = Column(String(255), nullable=True, comment="拒绝原因")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# 数据库初始化
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./images.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """创建所有表"""
    Base.metadata.create_all(bind=engine)
