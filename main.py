import ipaddress
import os
import socket
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import cv2
import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from parsers import extract_fields

app = FastAPI(title="Heyu License OCR", version="1.2.0")
_ocr_engine = None
_ENGINE_LABEL = "RapidOCR"

# 单张图片下载体积上限（字节），防止被诱导拉取超大响应耗尽磁盘/内存。
_MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024


def _require_internal_token(token: Optional[str]) -> None:
    """内网鉴权：仅当配置了 HEYU_OCR_TOKEN 时启用，要求调用方携带匹配的 X-Internal-Token。
    OCR 服务不应直接对公网开放；此 Token 为纵深防御，避免端口意外暴露后被任意调用。"""
    expected = os.environ.get("HEYU_OCR_TOKEN", "").strip()
    if not expected:
        return
    if not token or token.strip() != expected:
        raise HTTPException(status_code=401, detail="未授权访问")


def _allowed_local_roots() -> list[Path]:
    """允许通过 image_path / 本地 image_url 读取的根目录白名单。
    取自 HEYU_UPLOAD_ROOT 与 HEYU_ALLOWED_ROOTS（os.pathsep 分隔），
    未配置时回退到容器内的只读上传挂载点。"""
    raw_parts: list[str] = []
    for env in ("HEYU_UPLOAD_ROOT", "HEYU_ALLOWED_ROOTS"):
        value = os.environ.get(env, "").strip()
        if value:
            raw_parts.extend(value.split(os.pathsep))
    if not raw_parts:
        raw_parts = ["/www/server/heyu-cy/uploads/file"]
    roots: list[Path] = []
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        try:
            roots.append(Path(part).resolve())
        except OSError:
            continue
    return roots


def _resolve_within_roots(candidate: Path) -> Optional[Path]:
    """将候选路径解析为真实路径并校验其位于白名单根目录内，阻断 .. 穿越/软链接逃逸。"""
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    for root in _allowed_local_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    return None


def _assert_public_host(host: str) -> None:
    """SSRF 防护：解析主机名到 IP，拒绝指向私网/环回/链路本地/保留地址的目标，
    防止 OCR 服务被诱导访问云元数据、内网服务等。"""
    host = (host or "").strip().strip("[]")
    if not host:
        raise HTTPException(status_code=400, detail="image_url 主机无效")
    addrs: set[str] = set()
    try:
        ipaddress.ip_address(host)
        addrs.add(host)
    except ValueError:
        try:
            for info in socket.getaddrinfo(host, None):
                addrs.add(info[4][0])
        except socket.gaierror as exc:
            raise HTTPException(status_code=400, detail="image_url 域名无法解析") from exc
    if not addrs:
        raise HTTPException(status_code=400, detail="image_url 域名无法解析")
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise HTTPException(status_code=400, detail="image_url 目标地址无效")
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise HTTPException(status_code=400, detail="image_url 指向了非法的内网地址")


def get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"OCR 引擎未就绪: {exc}",
            ) from exc
        _ocr_engine = RapidOCR()
    return _ocr_engine


class ParseRequest(BaseModel):
    image_url: str = ""
    image_path: str = ""
    doc_type: str = Field(
        ...,
        description="business_license | id_card_front | id_card_back | food_license",
    )


class ParseResponse(BaseModel):
    doc_type: str
    fields: dict
    raw_text: str
    engine: str = _ENGINE_LABEL


def _download_image(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="image_url 协议不支持")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="image_url 主机无效")
    # 下单前校验目标 IP；关闭自动跟随重定向，避免重定向绕过 SSRF 校验。
    _assert_public_host(parsed.hostname)
    with httpx.Client(timeout=60.0, follow_redirects=False) as client:
        resp = client.get(url)
        if resp.is_redirect:
            raise HTTPException(status_code=400, detail="image_url 不允许重定向")
        resp.raise_for_status()
        content = resp.content
        if len(content) > _MAX_DOWNLOAD_BYTES:
            raise HTTPException(status_code=400, detail="image_url 文件过大")
        suffix = Path(parsed.path).suffix or ".jpg"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        Path(path).write_bytes(content)
        return path


def _resolve_image(req: ParseRequest) -> tuple[str, bool]:
    if req.image_path:
        resolved = _resolve_within_roots(Path(req.image_path))
        if resolved is None:
            raise HTTPException(status_code=400, detail="image_path 不存在或不在允许的目录内")
        return str(resolved), False
    if not req.image_url:
        raise HTTPException(status_code=400, detail="请提供 image_url 或 image_path")
    url = req.image_url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return _download_image(url), True
    # 非 http(s) 一律按受限本地路径处理，强制落在白名单根目录内。
    candidate = Path(url)
    if not candidate.is_absolute():
        roots = _allowed_local_roots()
        if roots:
            candidate = roots[0] / url.lstrip("/")
    resolved = _resolve_within_roots(candidate)
    if resolved is None:
        raise HTTPException(status_code=400, detail="无法定位图片文件或不在允许的目录内")
    return str(resolved), False


def _enhance(image):
    """灰度 + CLAHE 对比度增强：提升淡色字体 / 水印遮挡区域（如营业执照「名称」行）的检测召回。"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def _estimate_skew(image) -> float:
    """估计整页文本倾角（度，正值表示需逆时针纠正）。

    手机翻拍常带几度倾斜，RapidOCR 对此召回骤降。用 Hough 直线检测近水平线
    （证照矩形边框 + 文本行都是强水平特征）取中位角，比 minAreaRect 稳健且
    不会出现符号歧义（minAreaRect 的角度约定会把倾向纠反，反而加倍倾斜）。
    """
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    h, w = gray.shape[:2]
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=120,
        minLineLength=int(w * 0.3), maxLineGap=20,
    )
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in lines[:, 0]:
        ang = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(ang) < 20:  # 仅保留近水平线
            angles.append(ang)
    if not angles:
        return 0.0
    median = float(np.median(angles))
    # 仅纠正小角度整体倾斜，避免把竖排/异常版面误转。
    return 0.0 if abs(median) > 15 else median


def _deskew(image, angle: float):
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (w, h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )


def _ocr_lines(ocr, image) -> list[str]:
    result, _ = ocr(image)
    out: list[str] = []
    if not result:
        return out
    for item in result:
        if not item or len(item) < 2:
            continue
        text = str(item[1]).strip()
        if text:
            out.append(text)
    return out


def _run_ocr(image_path: str) -> list[str]:
    ocr = get_ocr()
    image = cv2.imread(image_path)
    if image is None:
        # 兜底：cv2 无法解码时仍交给 RapidOCR 直接读路径
        merged: list[str] = []
        for text in _ocr_lines(ocr, image_path):
            if text not in merged:
                merged.append(text)
        return merged
    # 多通道识别：原图 + CLAHE 增强图（+ 纠偏图，当检测到明显倾斜时），
    # 按行取并集去重，兼顾常规字段（原图）、淡色/水印遮挡字段（增强图，如「名称」）
    # 与倾斜翻拍件（纠偏图）。
    skew = _estimate_skew(image)
    if abs(skew) >= 0.5:
        # 检测到整体倾斜：纠偏图优先（并集按首次出现去重，靠前者被解析器优先采用），
        # 原图垫后兜底召回。
        corrected = _deskew(image, skew)
        frames = [corrected, _enhance(corrected), image]
    else:
        frames = [image, _enhance(image)]
    merged: list[str] = []
    for frame in frames:
        for text in _ocr_lines(ocr, frame):
            if text not in merged:
                merged.append(text)
    return merged


@app.get("/health")
def health():
    return {"status": "ok", "engine": _ENGINE_LABEL}


@app.post("/parse", response_model=ParseResponse)
def parse_license(req: ParseRequest, x_internal_token: Optional[str] = Header(default=None)):
    _require_internal_token(x_internal_token)
    allowed = {
        "business_license",
        "id_card_front",
        "id_card_back",
        "food_license",
    }
    if req.doc_type not in allowed:
        raise HTTPException(status_code=400, detail="doc_type 无效")
    image_path, is_temp = _resolve_image(req)
    try:
        lines = _run_ocr(image_path)
        fields = extract_fields(req.doc_type, lines)
        return ParseResponse(
            doc_type=req.doc_type,
            fields=fields,
            raw_text="\n".join(lines),
            engine=_ENGINE_LABEL,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"识别失败: {exc}") from exc
    finally:
        if is_temp:
            try:
                os.remove(image_path)
            except OSError:
                pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8091")))
