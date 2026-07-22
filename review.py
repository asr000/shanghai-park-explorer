"""
AI 图片审核模块

真实模式：调用阿里云视觉智能开放平台 - 场景识别 API
  开通地址：https://vision.aliyun.com/
  文档：https://help.aliyun.com/document_detail/294531.html

Mock 模式：当未配置 ALIBABA_CLOUD_ACCESS_KEY_ID 时自动降级
"""
import os
import random
import logging

logger = logging.getLogger(__name__)

import oss2

def _upload_to_oss(image_path: str) -> str:
    """上传图片到 OSS，返回公网 URL"""
    bucket_name = os.getenv("OSS_BUCKET_NAME", "")
    endpoint = os.getenv("OSS_ENDPOINT", "http://oss-cn-shanghai.aliyuncs.com")
    
    if not bucket_name:
        raise ValueError("未配置 OSS_BUCKET_NAME")
    
    auth = oss2.Auth(
        os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", ""),
        os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
    )
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    
    # 用文件 hash 作为 OSS 文件名，避免重复
    import hashlib
    with open(image_path, "rb") as f:
        content = f.read()
    file_hash = hashlib.md5(content).hexdigest()
    ext = os.path.splitext(image_path)[1]
    oss_key = f"park-photos/{file_hash}{ext}"
    
    bucket.put_object(oss_key, content)
    # 生成签名 URL（1 小时有效），私有 Bucket 也能用
    url = bucket.sign_url("GET", oss_key, 3600)
    logger.info(f"[OSS] 上传成功: {oss_key}")
    return url


# ---------- 风景/自然标签白名单 ----------
WHITELIST_TAGS = {
    # 英文标签
    "sky", "mountain", "ocean", "sea", "river", "lake",
    "forest", "park", "garden", "plant", "flower", "field",
    "grassland", "desert", "snow", "cloud", "sunset", "night",
    "star", "tree", "water", "landscape", "nature", "outdoor",
    "scenery", "sunrise", "autumn", "spring", "stream", "pond",
    "meadow", "woodland", "waterfall", "canyon", "coast", "island",
    # 中文标签
    "蓝天", "山脉", "大海", "河流", "湖泊", "森林",
    "公园", "花园", "植物", "花", "田野", "草原",
    "沙漠", "雪", "云", "日落", "夜晚", "星星",
    "树", "水", "风景", "自然", "户外", "景色",
    "日出", "秋天", "春天", "小溪", "池塘", "草地",
    "林地", "瀑布", "峡谷", "海岸", "岛屿", "绿植",
    "绿树", "草坪", "湖水", "江景", "河景",
}

# ---------- 明确拒绝标签 ----------
BLOCK_TAGS = {
    "car", "vehicle", "person", "people", "food", "dish",
    "document", "text", "screen", "indoor", "room", "building",
    "billboard", "advertisement", "qr", "barcode",
    "汽车", "人", "食物", "文档", "室内", "房间",
    "建筑", "广告牌", "二维码",
}


async def _review_real(image_path: str) -> tuple:
    """
    真实审核：调用阿里云场景识别 API
    返回 (status, score, tags)
    """
    # TODO: 在这里替换为真实的阿里云/腾讯云内容审核 API
    from aliyunsdkcore.client import AcsClient
    from aliyunsdkcore.request import CommonRequest
    import json

    access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")

    if not access_key_id or not access_key_secret:
        logger.warning("[审核] 未配置阿里云 AK，降级为 Mock 模式")
        return await _review_mock(image_path)

    # 创建客户端
    client = AcsClient(
        access_key_id,
        access_key_secret,
        "cn-shanghai"
    )


    # 构建场景识别请求
    request = CommonRequest()
    request.set_accept_format("json")
    request.set_domain("imagerecog.cn-shanghai.aliyuncs.com")
    request.set_method("POST")
    request.set_protocol_type("https")
    request.set_version("2019-09-30")
    request.set_action_name("RecognizeScene")
    # 上传到 OSS 获取公网 URL
    bucket_name = os.getenv("OSS_BUCKET_NAME", "")
    if bucket_name:
        image_url = _upload_to_oss(image_path)
    else:
        logger.warning("[审核] 未配置 OSS_BUCKET_NAME，无法使用 RecognizeScene，降级 Mock")
        return await _review_mock(image_path)
    request.add_body_params("ImageURL", image_url)

    try:
        response = client.do_action(request)
        result = json.loads(response)

        # 检查 API 是否返回错误（如 base64 不支持）
        if "Code" in result and result["Code"] != "0":
            code = result.get("Code", "UNKNOWN")
            msg = result.get("Message", "")
            logger.warning(f"[审核] API 返回错误: {code} - {msg}")
            if "ImageURL" in msg or "InvalidImage" in code:
                logger.warning("[审核] RecognizeScene 仅支持 OSS URL，当前使用 base64 不受支持，降级 Mock")
            return await _review_mock(image_path)

        logger.info(f"[审核] API 返回: {json.dumps(result, ensure_ascii=False)}")

        # 解析标签
        tags_data = result.get("Data", {}).get("Tags", [])
        tags = [t.get("Value", "") for t in tags_data]
        scores = {t.get("Value", ""): t.get("Confidence", 0) for t in tags_data}

        if not tags_data:
            return ("rejected", 0, [], "未识别到任何标签")

        # 获取最高置信度
        max_score = max((t.get("Confidence", 0) for t in tags_data), default=0)
        ai_score = round(max_score, 2)

        # 置信度低于 60% -> 拒绝
        if max_score < 60:
            return ("rejected", ai_score, tags, f"最高置信度过低 ({ai_score}% < 60%)")

        # 命中白名单 -> 通过
        for tag in tags:
            if tag in WHITELIST_TAGS:
                return ("approved", ai_score, tags, None)

        # 命中屏蔽标签 -> 拒绝
        for tag in tags:
            if tag in BLOCK_TAGS:
                return ("rejected", ai_score, tags, f"检测到不合适标签: {tag}")

        # 都不匹配 -> 拒绝
        return ("rejected", ai_score, tags, "标签不在风景白名单中")

    except Exception as e:
        logger.warning(f"[审核] API 调用失败 ({e})，降级为 Mock 模式")
        return await _review_mock(image_path)


async def _review_mock(image_path: str) -> tuple:
    """
    Mock 审核：基于文件名的简单判断 + 随机结果
    概率：60% 通过，40% 拒绝
    """
    import hashlib

    # 基于文件名哈希做伪随机（保证同一文件结果一致）
    basename = os.path.basename(image_path)
    hash_val = int(hashlib.md5(basename.encode()).hexdigest(), 16)

    # 60% 通过概率
    approved = (hash_val % 100) < 60
    score = round(60 + (hash_val % 40), 2)  # 模拟 60-100 的分数

    # 模拟标签
    mock_tags_pool = ["tree", "park", "garden", "flower", "landscape", "sky",
                      "lake", "mountain", "plant", "forest", "grassland"]
    mock_tags = random.sample(mock_tags_pool, min(3, len(mock_tags_pool)))

    if approved:
        logger.info(f"[Mock审核] ✅ 通过: {basename} (score={score})")
        return ("approved", score, mock_tags, None)
    else:
        # 拒绝原因随机选取
        reasons = ["标签不在风景白名单中", "置信度过低", "检测到非风景内容"]
        reason = reasons[hash_val % len(reasons)]
        logger.info(f"[Mock审核] ❌ 拒绝: {basename} - {reason}")
        return ("rejected", score, [], reason)


async def review_image(image_path: str) -> tuple:
    """
    审核图片入口
    返回: (status: str, score: float, tags: list, reason: str|None)
    """
    try:
        return await _review_real(image_path)
    except Exception as e:
        logger.warning(f"[审核] 异常降级 Mock: {e}")
        return await _review_mock(image_path)
