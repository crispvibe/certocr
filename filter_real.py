"""对 test_images/real/ 下载图做快速 OCR 过滤，挑出"真正是填好数据的营业执照"的候选。

判定标准：OCR 文本同时含「营业执照」关键词 + 能抽到 18 位统一社会信用代码 + 能抽到名称。
单帧 OCR（不做增强/纠偏）以求速度，结果写入 real/_candidates.json。
"""

import json
import re
from pathlib import Path

import cv2

import main as ocr_main
from parsers import extract_fields

REAL = Path(__file__).parent / "test_images" / "real"


def ocr_once(path):
    eng = ocr_main.get_ocr()
    img = cv2.imread(str(path))
    if img is None:
        return []
    return ocr_main._ocr_lines(eng, img)


def main():
    imgs = sorted([p for p in REAL.glob("*")
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    print(f"过滤 {len(imgs)} 张 ...")
    cands = []
    for i, p in enumerate(imgs, 1):
        try:
            lines = ocr_once(p)
        except Exception as e:
            print(f"[{i}/{len(imgs)}] {p.name} OCR错误 {e}")
            continue
        text = "\n".join(lines)
        has_kw = "营业执照" in text or "信用代码" in text or "市场监督" in text
        f = extract_fields("business_license", lines)
        code_ok = bool(re.fullmatch(r"[0-9A-Z]{18}", f.get("credit_code", "")))
        name_ok = len(f.get("name", "")) >= 4
        score = sum([has_kw, code_ok, name_ok])
        if score >= 2:
            cands.append({
                "file": p.name, "score": score,
                "has_kw": has_kw, "code_ok": code_ok, "name_ok": name_ok,
                "fields": f, "raw_text": text,
            })
        flag = "*" if score >= 2 else " "
        print(f"[{i:>3}/{len(imgs)}] {flag} score={score} {p.name}")
    cands.sort(key=lambda c: -c["score"])
    (REAL / "_candidates.json").write_text(
        json.dumps(cands, ensure_ascii=False, indent=2))
    print(f"\n候选 {len(cands)} 张 -> _candidates.json")
    for c in cands:
        print(f"  {c['file']:<14} score={c['score']} "
              f"name={c['fields'].get('name','')[:20]!r} "
              f"code={c['fields'].get('credit_code','')}")


if __name__ == "__main__":
    main()
