"""跑真实 RapidOCR 引擎 + parsers.extract_fields，对生成的营业执照测试图评测识别率。

用法：
    .venv/bin/python eval_ocr.py            # 跑全部生成图
    .venv/bin/python eval_ocr.py --variant clean   # 只跑清晰版

每张图与同名 .json 真值比对，输出逐字段识别率、按退化类型分组的识别率，
以及失败样本明细，结果写入 test_images/generated/_report.json。
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import main as ocr_main
from parsers import extract_fields

GEN_DIR = Path(__file__).parent / "test_images" / "generated"

# 评测字段：parser 实际会抽取的结构化字段
FIELDS = ["credit_code", "name", "legal_person", "address",
          "valid_from", "expired_at", "is_long_term"]


def _norm(s) -> str:
    if isinstance(s, bool):
        return str(s)
    return re.sub(r"\s+", "", str(s or "")).replace("(", "（").replace(")", "）")


def _match(field: str, got, want) -> bool:
    if field == "is_long_term":
        return bool(got) == bool(want)
    g, w = _norm(got), _norm(want)
    if field == "credit_code":
        return g.upper() == w.upper()
    if field == "address":
        # 地址较长，允许「真值包含识别值」或反之的高重合（OCR 偶尔吞尾字）
        if not w:
            return g == ""
        return g == w or (len(g) >= 6 and (g in w or w in g))
    return g == w


def evaluate(variant_filter=None):
    images = sorted(GEN_DIR.glob("lic_*.png"))
    if variant_filter:
        images = [p for p in images if p.stem.endswith("_" + variant_filter)]
    if not images:
        raise SystemExit(f"没有找到测试图，请先运行 gen_licenses.py（dir={GEN_DIR}）")

    field_stats = {f: [0, 0] for f in FIELDS}          # field -> [correct, total]
    variant_stats = defaultdict(lambda: [0, 0])        # variant -> [correct_fields, total_fields]
    record_full_correct = 0
    details = []

    print(f"评测 {len(images)} 张图 ...\n")
    for idx, img in enumerate(images, 1):
        gt = json.loads(img.with_suffix(".json").read_text())
        lines = ocr_main._run_ocr(str(img))
        got = extract_fields("business_license", lines)

        per = {}
        all_core_ok = True
        for f in FIELDS:
            ok = _match(f, got.get(f), gt.get(f))
            per[f] = ok
            field_stats[f][1] += 1
            variant_stats[gt["variant"]][1] += 1
            if ok:
                field_stats[f][0] += 1
                variant_stats[gt["variant"]][0] += 1
            if f in ("credit_code", "name", "legal_person") and not ok:
                all_core_ok = False
        if all_core_ok:
            record_full_correct += 1

        details.append({
            "image": img.name,
            "variant": gt["variant"],
            "per_field": per,
            "expected": {f: gt.get(f) for f in FIELDS},
            "got": {f: got.get(f) for f in FIELDS},
            "raw_text": "\n".join(lines),
        })
        flag = "OK " if all(per.values()) else "DIFF"
        print(f"[{idx:>3}/{len(images)}] {flag} {img.name:<24} "
              + " ".join(f"{f}={'1' if per[f] else '0'}" for f in FIELDS))

    print("\n================ 逐字段识别率 ================")
    for f in FIELDS:
        c, t = field_stats[f]
        print(f"  {f:<14} {c:>3}/{t:<3}  {c / t * 100:5.1f}%")

    print("\n================ 按退化类型 ================")
    for v in sorted(variant_stats):
        c, t = variant_stats[v]
        print(f"  {v:<8} 字段识别率 {c}/{t}  {c / t * 100:5.1f}%")

    total_c = sum(s[0] for s in field_stats.values())
    total_t = sum(s[1] for s in field_stats.values())
    print("\n================ 汇总 ================")
    print(f"  总字段识别率      {total_c}/{total_t}  {total_c / total_t * 100:5.1f}%")
    print(f"  核心三项全对的图   {record_full_correct}/{len(images)}  "
          f"{record_full_correct / len(images) * 100:5.1f}%  (名称+信用代码+法定代表人)")

    report = {
        "n_images": len(images),
        "field_accuracy": {f: {"correct": field_stats[f][0], "total": field_stats[f][1],
                               "rate": round(field_stats[f][0] / field_stats[f][1], 4)}
                           for f in FIELDS},
        "variant_accuracy": {v: {"correct": variant_stats[v][0], "total": variant_stats[v][1],
                                 "rate": round(variant_stats[v][0] / variant_stats[v][1], 4)}
                             for v in sorted(variant_stats)},
        "overall_field_rate": round(total_c / total_t, 4),
        "core_full_correct": record_full_correct,
        "details": details,
    }
    (GEN_DIR / "_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n明细已写入 {GEN_DIR / '_report.json'}")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default=None,
                    help="只评测某个退化类型：clean/blur/jpeg/rotate/dark/small")
    args = ap.parse_args()
    evaluate(args.variant)
