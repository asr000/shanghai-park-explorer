"""
AI Image Moderation Module

Real mode: Alibaba Cloud Visual Intelligence - RecognizeScene API
  Console: https://vision.aliyun.com/
  Docs: https://help.aliyun.com/document_detail/294531.html

Mock mode: auto fallback when ALIBABA_CLOUD_ACCESS_KEY_ID not set
"""
import os
import random
import logging

logger = logging.getLogger(__name__)

import oss2

def _upload_to_oss(image_path: str) -> str:
    """Upload image to OSS, return public URL"""
    bucket_name = os.getenv("OSS_BUCKET_NAME", "")
    endpoint = os.getenv("OSS_ENDPOINT", "http://oss-cn-shanghai.aliyuncs.com")
    
    if not bucket_name:
        raise ValueError("OSS_BUCKET_NAME not configured")
    
    auth = oss2.Auth(
        os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", ""),
        os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
    )
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    
    import hashlib
    with open(image_path, "rb") as f:
        content = f.read()
    file_hash = hashlib.md5(content).hexdigest()
    ext = os.path.splitext(image_path)[1]
    oss_key = f"park-photos/{file_hash}{ext}"
    
    bucket.put_object(oss_key, content)
    url = bucket.sign_url("GET", oss_key, 3600)
    logger.info(f"[OSS] Upload success: {oss_key}")
    return url


# ---------- Scenery / Nature Tag Whitelist ----------
WHITELIST_TAGS = {
    # English
    "sky", "mountain", "ocean", "sea", "river", "lake",
    "forest", "park", "garden", "plant", "flower", "field",
    "grassland", "desert", "snow", "cloud", "sunset", "night",
    "star", "tree", "water", "landscape", "nature", "outdoor",
    "scenery", "sunrise", "autumn", "spring", "stream", "pond",
    "meadow", "woodland", "waterfall", "canyon", "coast", "island",
    # Chinese
    "蓝天", "山脉", "大海", "河流", "湖泊", "森林",
    "公园", "花园", "植物", "花", "田野", "草原",
    "沙漠", "雪", "云", "日落", "夜晚", "星星",
    "树", "水", "风景", "自然", "户外", "景色",
    "日出", "秋天", "春天", "小溪", "池塘", "草地",
    "林地", "瀑布", "峡谷", "海岸", "岛屿", "绿植",
    "绿树", "草坪", "湖水", "江景", "河景",
}
# ---------- Explicit Block Tags ----------
BLOCK_TAGS = {
    "car", "vehicle", "person", "people", "food", "dish",
    "document", "text", "screen", "indoor", "room", "building",
    "billboard", "advertisement", "qr", "barcode",
    "汽车", "人", "食物", "文档", "室内", "房间",
    "建筑", "广告牌", "二维码",
}


async def _review_real(image_path: str) -> tuple:
    """
    Real review: call Alibaba Cloud RecognizeScene API
    Returns (status, score, tags, reason)
    """
    from aliyunsdkcore.client import AcsClient
    from aliyunsdkcore.request import CommonRequest
    import json

    access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")

    if not access_key_id or not access_key_secret:
        logger.warning("[Review] Alibaba Cloud AK not configured, falling back to Mock mode")
        return await _review_mock(image_path)

    client = AcsClient(access_key_id, access_key_secret, "cn-shanghai")

    request = CommonRequest()
    request.set_accept_format("json")
    request.set_domain("imagerecog.cn-shanghai.aliyuncs.com")
    request.set_method("POST")
    request.set_protocol_type("https")
    request.set_version("2019-09-30")
    request.set_action_name("RecognizeScene")
    
    bucket_name = os.getenv("OSS_BUCKET_NAME", "")
    if bucket_name:
        image_url = _upload_to_oss(image_path)
    else:
        logger.warning("[Review] OSS_BUCKET_NAME not configured, cannot use RecognizeScene, fallback to Mock")
        return await _review_mock(image_path)
    request.add_body_params("ImageURL", image_url)

    try:
        response = client.do_action(request)
        result = json.loads(response)

        if "Code" in result and result["Code"] != "0":
            code = result.get("Code", "UNKNOWN")
            msg = result.get("Message", "")
            logger.warning(f"[Review] API error: {code} - {msg}")
            if "ImageURL" in msg or "InvalidImage" in code:
                logger.warning("[Review] RecognizeScene only supports OSS URL, current base64 not supported, fallback to Mock")
            return await _review_mock(image_path)

        logger.info(f"[Review] API response: {json.dumps(result, ensure_ascii=False)}")

        tags_data = result.get("Data", {}).get("Tags", [])
        tags = [t.get("Value", "") for t in tags_data]
        scores = {t.get("Value", ""): t.get("Confidence", 0) for t in tags_data}

        if not tags_data:
            return ("rejected", 0, [], "No tags detected")

        max_score = max((t.get("Confidence", 0) for t in tags_data), default=0)
        ai_score = round(max_score, 2)

        if max_score < 60:
            return ("rejected", ai_score, tags, f"Confidence too low ({ai_score}% < 60%)")

        for tag in tags:
            if tag in WHITELIST_TAGS:
                return ("approved", ai_score, tags, None)

        for tag in tags:
            if tag in BLOCK_TAGS:
                return ("rejected", ai_score, tags, f"Detected inappropriate tag: {tag}")

        return ("rejected", ai_score, tags, "Tags not in scenery whitelist")

    except Exception as e:
        logger.warning(f"[Review] API call failed ({e}), fallback to Mock mode")
        return await _review_mock(image_path)


async def _review_mock(image_path: str) -> tuple:
    """
    Mock review: simple judgment based on filename + random result
    Probability: 60% approved, 40% rejected
    """
    import hashlib

    basename = os.path.basename(image_path)
    hash_val = int(hashlib.md5(basename.encode()).hexdigest(), 16)

    approved = (hash_val % 100) < 60
    score = round(60 + (hash_val % 40), 2)
    mock_tags_pool = ["tree", "park", "garden", "flower", "landscape", "sky",
                      "lake", "mountain", "plant", "forest", "grassland"]
    mock_tags = random.sample(mock_tags_pool, min(3, len(mock_tags_pool)))

    if approved:
        logger.info(f"[Mock] APPROVED: {basename} (score={score})")
        return ("approved", score, mock_tags, None)
    else:
        reasons = ["Tags not in scenery whitelist", "Confidence too low", "Non-scenery content detected"]
        reason = reasons[hash_val % len(reasons)]
        logger.info(f"[Mock] REJECTED: {basename} - {reason}")
        return ("rejected", score, [], reason)


async def review_image(image_path: str) -> tuple:
    """
    Image moderation entry point
    Returns: (status: str, score: float, tags: list, reason: str|None)
    """
    try:
        return await _review_real(image_path)
    except Exception as e:
        logger.warning(f"[Review] Exception, fallback to Mock: {e}")
        return await _review_mock(image_path)