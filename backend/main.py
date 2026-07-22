"""
上海公园探索器 - 图片审核后端
启动: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from models import init_db, SessionLocal, ImagePost, ImageStatus
from review import review_image

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 静态文件目录
UPLOAD_DIR = Path("./static/imgs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("✅ 数据库初始化完成")
    yield


app = FastAPI(title="上海公园图片审核", version="1.0.0", lifespan=lifespan)

# CORS - 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://asr000.github.io",
        "https://shanghai-park-explorer-production.up.railway.app",
        "https://*.railway.app",
        "https://*.up.railway.app",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件服务
app.mount("/static", StaticFiles(directory="static"), name="static")


async def _do_review(image_id: int, image_path: str):
    """后台审核任务"""
    db = SessionLocal()
    try:
        post = db.get(ImagePost, image_id)
        if not post:
            logger.error(f"审核任务: 找不到 id={image_id}")
            return

        logger.info(f"🔍 开始审核: {post.filename}")
        status, score, tags, reason = await review_image(image_path)

        post.status = ImageStatus(status)
        post.ai_score = score
        post.ai_tags = ",".join(tags) if tags else None
        post.reject_reason = reason
        db.commit()

        if status == "approved":
            logger.info(f"✅ 审核通过: {post.filename} (score={score})")
        else:
            logger.info(f"❌ 审核拒绝: {post.filename} - {reason}")
    except Exception as e:
        logger.error(f"审核异常: {e}")
    finally:
        db.close()


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    上传图片
    - 保存到 ./static/imgs/
    - 立即返回 {"id": ..., "status": "pending"}
    - 后台异步审核
    """
    # 校验文件类型
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {file.content_type}")

    # 生成唯一文件名
    ext = Path(file.filename).suffix or ".jpg"
    new_name = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / new_name

    # 保存文件
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    # 写入数据库
    db = SessionLocal()
    try:
        post = ImagePost(
            filename=file.filename,
            filepath=str(save_path.relative_to("static")),
            status=ImageStatus.PENDING,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        image_id = post.id
    finally:
        db.close()

    # 异步后台审核
    background_tasks.add_task(_do_review, image_id, str(save_path))

    return {
        "msg": "upload success",
        "id": image_id,
        "filename": file.filename,
        "status": "pending",
    }


@app.get("/list")
async def list_images(status: str = "approved"):
    """
    获取审核结果列表
    ?status=approved  - 通过的（默认）
    ?status=pending   - 审核中的
    ?status=all       - 全部
    """
    db = SessionLocal()
    try:
        query = select(ImagePost).order_by(ImagePost.created_at.desc())

        if status != "all":
            query = query.where(ImagePost.status == status)

        posts = db.execute(query).scalars().all()

        return [{
            "id": p.id,
            "filename": p.filename,
            "filepath": p.filepath,
            "url": f"/static/{p.filepath}",
            "status": p.status.value,
            "ai_score": p.ai_score,
            "ai_tags": p.ai_tags,
            "reject_reason": p.reject_reason,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        } for p in posts]
    finally:
        db.close()


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
