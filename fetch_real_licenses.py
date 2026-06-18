"""从 360 图片搜索抓取真实/仿真营业执照图片，落地到 test_images/real/ 供 OCR 评测。

注意：这些图片仅用于本地评测 OCR 识别率，不作他用。
用法：
    .venv/bin/python fetch_real_licenses.py
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs, unquote

import httpx

OUT = Path(__file__).parent / "test_images" / "real"
OUT.mkdir(parents=True, exist_ok=True)

QUERIES = [
    "营业执照样本",
    "营业执照副本",
    "个体工商户营业执照",
    "新版营业执照",
    "营业执照 高清 有限公司",
    "公司营业执照正本",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://image.so.com/",
}


def unwrap(url: str) -> str:
    # 网易/有道等会用 ?url= 包一层，取真实地址
    if "url=" in url:
        q = parse_qs(urlparse(url).query)
        if "url" in q:
            return unquote(q["url"][0])
    return url


def collect_urls():
    urls = []
    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as cli:
        for q in QUERIES:
            for pn in (0, 30, 60):
                api = f"https://image.so.com/j?q={quote(q)}&pn={pn}&src=srp"
                try:
                    data = cli.get(api).json()
                except Exception as e:
                    print("query fail", q, pn, e)
                    continue
                for it in data.get("list", []):
                    u = it.get("img") or it.get("thumb")
                    if u:
                        urls.append((unwrap(u), it.get("title", "")))
                time.sleep(0.3)
    # 去重
    seen, out = set(), []
    for u, t in urls:
        if u not in seen:
            seen.add(u)
            out.append((u, t))
    return out


def download(urls):
    saved = []
    with httpx.Client(headers=HEADERS, timeout=40.0, follow_redirects=True) as cli:
        for i, (u, t) in enumerate(urls):
            ext = Path(urlparse(u).path).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            dst = OUT / f"web_{i:03d}{ext}"
            try:
                r = cli.get(u)
                r.raise_for_status()
                if len(r.content) < 8000:  # 跳过过小的缩略图/占位图
                    continue
                dst.write_bytes(r.content)
                saved.append((dst.name, len(r.content), t))
            except Exception as e:
                print("dl fail", u[:80], e)
    return saved


if __name__ == "__main__":
    urls = collect_urls()
    print(f"收集到 {len(urls)} 个候选 URL")
    saved = download(urls)
    print(f"下载 {len(saved)} 张：")
    for name, size, title in saved:
        print(f"  {name:<14} {size:>8}B  {title[:40]}")
    (OUT / "_manifest.json").write_text(
        json.dumps([{"file": n, "title": t} for n, _, t in saved],
                   ensure_ascii=False, indent=2))
