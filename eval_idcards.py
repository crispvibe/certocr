"""跑真实 RapidOCR + parsers.extract_fields，评测身份证正/反面识别率。

用法：.venv/bin/python eval_idcards.py [--variant clean]
结果写入 test_images/idcards/_report.json。
"""

import argparse
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import main as ocr_main
from parsers import extract_fields

GEN_DIR = Path(__file__).parent / "test_images" / "idcards"

FIELDS_FRONT = ["name", "id_number", "address"]
FIELDS_BACK = ["valid_from", "expired_at", "is_long_term"]


def _norm(s) -> str:
    if isinstance(s, bool):
        return str(s)
    return re.sub(r"\s+", "", str(s or ""))


def _match(field, got, want) -> bool:
    if field == "is_long_term":
        return bool(got) == bool(want)
    g, w = _norm(got), _norm(want)
    if field == "id_number":
        return g.upper() == w.upper()
    if field == "address":
        if not w:
            return g == ""
        # 严格些：要求整段高度一致（≥0.9 相似度），仅识别首行不算过。
        return g == w or SequenceMatcher(None, g, w).ratio() >= 0.9
    return g == w


def evaluate(variant_filter=None):
    images = sorted(GEN_DIR.glob("id_*.png"))
    if variant_filter:
        images = [p for p in images if p.stem.endswith("_" + variant_filter)]
    if not images:
        raise SystemExit(f"无测试图，请先运行 gen_idcards.py（{GEN_DIR}）")

    field_stats = defaultdict(lambda: [0, 0])
    variant_stats = defaultdict(lambda: [0, 0])
    side_stats = defaultdict(lambda: [0, 0])
    details = []

    print(f"评测 {len(images)} 张身份证图 ...\n")
    for idx, img in enumerate(images, 1):
        gt = json.loads(img.with_suffix(".json").read_text(encoding="utf-8"))
        doc_type = gt["doc_type"]
        side = "front" if doc_type == "id_card_front" else "back"
        fields = FIELDS_FRONT if side == "front" else FIELDS_BACK

        lines = ocr_main._run_ocr(str(img))
        got = extract_fields(doc_type, lines)

        per = {}
        for f in fields:
            ok = _match(f, got.get(f), gt.get(f))
            per[f] = ok
            field_stats[f][1] += 1
            variant_stats[gt["variant"]][1] += 1
            side_stats[side][1] += 1
            if ok:
                field_stats[f][0] += 1
                variant_stats[gt["variant"]][0] += 1
                side_stats[side][0] += 1

        details.append({
            "image": img.name, "variant": gt["variant"], "side": side,
            "per_field": per,
            "expected": {f: gt.get(f) for f in fields},
            "got": {f: got.get(f) for f in fields},
            "raw_text": "\n".join(lines),
        })
        flag = "OK " if all(per.values()) else "DIFF"
        print(f"[{idx:>3}/{len(images)}] {flag} {img.name:<26} "
              + " ".join(f"{f}={'1' if per[f] else '0'}" for f in fields))

    print("\n================ 逐字段识别率 ================")
    for f in FIELDS_FRONT + FIELDS_BACK:
        c, t = field_stats[f]
        if t:
            print(f"  {f:<14} {c:>3}/{t:<3}  {c / t * 100:5.1f}%")

    print("\n================ 正面 / 反面 ================")
    for s in ("front", "back"):
        c, t = side_stats[s]
        print(f"  {s:<6} {c}/{t}  {c / t * 100:5.1f}%")

    print("\n================ 按退化类型 ================")
    for v in sorted(variant_stats):
        c, t = variant_stats[v]
        print(f"  {v:<8} {c}/{t}  {c / t * 100:5.1f}%")

    total_c = sum(s[0] for s in field_stats.values())
    total_t = sum(s[1] for s in field_stats.values())
    print("\n================ 汇总 ================")
    print(f"  总字段识别率  {total_c}/{total_t}  {total_c / total_t * 100:5.1f}%")

    report = {
        "n_images": len(images),
        "field_accuracy": {f: {"correct": field_stats[f][0], "total": field_stats[f][1],
                               "rate": round(field_stats[f][0] / field_stats[f][1], 4)}
                           for f in field_stats if field_stats[f][1]},
        "side_accuracy": {s: {"correct": side_stats[s][0], "total": side_stats[s][1],
                              "rate": round(side_stats[s][0] / side_stats[s][1], 4)}
                          for s in side_stats},
        "variant_accuracy": {v: {"correct": variant_stats[v][0], "total": variant_stats[v][1],
                                 "rate": round(variant_stats[v][0] / variant_stats[v][1], 4)}
                             for v in sorted(variant_stats)},
        "overall_field_rate": round(total_c / total_t, 4),
        "details": details,
    }
    (GEN_DIR / "_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细已写入 {GEN_DIR / '_report.json'}")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default=None)
    args = ap.parse_args()
    evaluate(args.variant)
