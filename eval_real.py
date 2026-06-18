"""用真实下载的营业执照图 + 人工标注真值，评测完整 OCR 流水线的识别率。

真值文件：test_images/real/_ground_truth.json
跑的是 main._run_ocr（含多帧增强/纠偏）+ parsers.extract_fields，贴近线上效果。
结果写入 test_images/real/_real_report.json。
"""

import json
import re
from collections import defaultdict
from pathlib import Path

import main as ocr_main
from parsers import extract_fields

REAL = Path(__file__).parent / "test_images" / "real"
GT_FILE = REAL / "_ground_truth.json"

FIELDS = ["credit_code", "name", "legal_person", "address",
          "valid_from", "expired_at", "is_long_term"]


def _norm(s) -> str:
    if isinstance(s, bool):
        return str(s)
    return re.sub(r"\s+", "", str(s or "")).replace("(", "（").replace(")", "）")


def _match(field, got, want) -> bool:
    if field == "is_long_term":
        return bool(got) == bool(want)
    g, w = _norm(got), _norm(want)
    if field == "credit_code":
        return g.upper() == w.upper()
    if field == "address":
        if not w:
            return g == ""
        return g == w or (len(g) >= 6 and (g in w or w in g))
    if field == "name":
        if not w:
            return g == ""
        return g == w or (len(g) >= 4 and (g in w or w in g))
    return g == w


def main():
    gt = json.loads(GT_FILE.read_text())
    field_stats = {f: [0, 0] for f in FIELDS}
    details = []
    core_full = 0

    print(f"评测 {len(gt)} 张真实执照 ...\n")
    for i, (fname, truth) in enumerate(sorted(gt.items()), 1):
        img = REAL / fname
        if not img.is_file():
            print(f"  缺图 {fname}")
            continue
        lines = ocr_main._run_ocr(str(img))
        got = extract_fields("business_license", lines)

        per = {}
        core_ok = True
        for f in FIELDS:
            ok = _match(f, got.get(f), truth.get(f))
            per[f] = ok
            field_stats[f][1] += 1
            if ok:
                field_stats[f][0] += 1
            if f in ("credit_code", "name", "legal_person") and not ok:
                core_ok = False
        if core_ok:
            core_full += 1

        details.append({
            "image": fname, "note": truth.get("note", ""),
            "per_field": per,
            "expected": {f: truth.get(f) for f in FIELDS},
            "got": {f: got.get(f) for f in FIELDS},
            "raw_text": "\n".join(lines),
        })
        flag = "OK  " if core_ok else "MISS"
        print(f"[{i:>2}/{len(gt)}] {flag} {fname:<14} "
              + " ".join(f"{f.split('_')[0]}={'1' if per[f] else '0'}" for f in FIELDS))

    print("\n================ 逐字段识别率（真实图）================")
    for f in FIELDS:
        c, t = field_stats[f]
        print(f"  {f:<14} {c:>2}/{t:<2}  {c / t * 100:5.1f}%")

    total_c = sum(s[0] for s in field_stats.values())
    total_t = sum(s[1] for s in field_stats.values())
    print("\n================ 汇总 ================")
    print(f"  总字段识别率     {total_c}/{total_t}  {total_c / total_t * 100:5.1f}%")
    print(f"  核心三项全对的图  {core_full}/{len(gt)}  {core_full / len(gt) * 100:5.1f}%"
          f"  (名称+信用代码+法定代表人)")

    report = {
        "n_images": len(gt),
        "field_accuracy": {f: {"correct": field_stats[f][0], "total": field_stats[f][1],
                               "rate": round(field_stats[f][0] / field_stats[f][1], 4)}
                           for f in FIELDS},
        "overall_field_rate": round(total_c / total_t, 4),
        "core_full_correct": core_full,
        "details": details,
    }
    (REAL / "_real_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n明细已写入 {REAL / '_real_report.json'}")


if __name__ == "__main__":
    main()
