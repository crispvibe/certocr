"""生成带「真值」的身份证正/反面测试图，用于评测 OCR 识别率。

正面：姓名 / 性别 / 民族 / 出生 / 住址（含换行）/ 公民身份号码。
反面：签发机关 / 有效期限（含「长期」）。
身份证号带合法 ISO 7064 mod 11-2 校验位、且与出生日期/性别一致。
每张图配同名 .json 真值，供 eval_idcards.py 比对。
退化版本模拟手机翻拍：模糊 / JPEG / 旋转4° / 偏暗 / 缩小。
"""

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

OUT_DIR = Path(__file__).parent / "test_images" / "idcards"

FONT_HEI = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_HEI_L = "/System/Library/Fonts/STHeiti Light.ttc"
FONT_SONG = "/System/Library/Fonts/Supplemental/Songti.ttc"

_SURNAMES = list("王李张刘陈杨黄赵周吴徐孙马朱胡郭何高林郑谢罗唐宋")
_GIVEN = ["伟", "芳", "娜", "敏", "静", "强", "磊", "军", "洋", "勇", "艳", "杰",
          "建国", "雪锋", "志强", "桂英", "秀兰", "晓明", "丽娟"]
_NATION = ["汉", "汉", "汉", "回", "满", "壮", "蒙古", "维吾尔"]

# (区划码6位, 住址模板, 签发机关)
_REGION = [
    ("110105", "北京市朝阳区呼家楼街道东三环{}号院{}号楼{}单元{}号", "北京市公安局朝阳分局"),
    ("310115", "上海市浦东新区张江镇科苑路{}弄{}号{}室", "上海市公安局浦东分局"),
    ("440106", "广东省广州市天河区天河南街道天河路{}号{}房", "广州市公安局天河分局"),
    ("440305", "广东省深圳市南山区粤海街道科技园路{}号{}栋{}室", "深圳市公安局南山分局"),
    ("530102", "云南省昆明市五华区华山街道东风西路{}号{}单元{}号", "昆明市公安局五华分局"),
    ("510107", "四川省成都市武侯区浆洗街街道人民南路{}段{}号{}号", "成都市公安局武侯分局"),
]

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK = "10X98765432"


def _id_check(first17: str) -> str:
    s = sum(int(c) * w for c, w in zip(first17, _ID_WEIGHTS))
    return _ID_CHECK[s % 11]


def _rand_id(region: str):
    y = random.randint(1955, 2004)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    seq = random.randint(0, 999)
    sex = "男" if seq % 2 == 1 else "女"
    body = f"{region}{y:04d}{m:02d}{d:02d}{seq:03d}"
    code = body + _id_check(body)
    return code, f"{y}年{m}月{d}日", sex


def make_front():
    region = random.choice(_REGION)
    code, birth, sex = _rand_id(region[0])
    name = random.choice(_SURNAMES) + random.choice(_GIVEN)
    addr_tpl = region[1]
    addr = addr_tpl.format(*[random.randint(1, 99) for _ in range(addr_tpl.count("{}"))])
    return {
        "doc_type": "id_card_front",
        "name": name,
        "sex": sex,
        "nation": random.choice(_NATION),
        "birth": birth,
        "address": addr,
        "id_number": code,
        "register_org": region[2],
    }


def make_back(front):
    y = random.randint(2012, 2020)
    m, d = random.randint(1, 12), random.randint(1, 28)
    if random.random() < 0.3:
        period = f"{y}.{m:02d}.{d:02d}-长期"
        vfrom, vto, longterm = f"{y:04d}-{m:02d}-{d:02d}", "", True
    else:
        ey = y + random.choice([10, 20])
        period = f"{y}.{m:02d}.{d:02d}-{ey}.{m:02d}.{d:02d}"
        vfrom, vto, longterm = f"{y:04d}-{m:02d}-{d:02d}", f"{ey:04d}-{m:02d}-{d:02d}", False
    return {
        "doc_type": "id_card_back",
        "register_org": front["register_org"],
        "period_text": period,
        "valid_from": vfrom,
        "expired_at": vto,
        "is_long_term": longterm,
    }


def _font(path, size):
    return ImageFont.truetype(path, size)


def render_front(rec, path: Path):
    W, H = 1010, 640
    img = Image.new("RGB", (W, H), (252, 250, 245))
    d = ImageDraw.Draw(img)
    # 淡色底纹（长城/水印感）
    wm = _font(FONT_HEI, 30)
    for yy in range(40, H, 70):
        d.text((30, yy), "中国 CHINA 居民身份证 " * 2, font=wm, fill=(238, 234, 226))
    d = ImageDraw.Draw(img)

    lab = _font(FONT_HEI_L, 26)
    val = _font(FONT_SONG, 30)
    lx, vx = 70, 210
    d.text((lx, 70), "姓　名", font=lab, fill=(50, 50, 50))
    d.text((vx, 66), rec["name"], font=val, fill=(20, 20, 20))

    d.text((lx, 150), "性　别", font=lab, fill=(50, 50, 50))
    d.text((vx, 146), rec["sex"], font=val, fill=(20, 20, 20))
    d.text((vx + 130, 150), "民　族", font=lab, fill=(50, 50, 50))
    d.text((vx + 300, 146), rec["nation"], font=val, fill=(20, 20, 20))

    d.text((lx, 230), "出　生", font=lab, fill=(50, 50, 50))
    d.text((vx, 226), rec["birth"], font=val, fill=(20, 20, 20))

    d.text((lx, 310), "住　址", font=lab, fill=(50, 50, 50))
    # 住址换行：每行约 11 个汉字
    addr = rec["address"]
    line_len = 11
    lines = [addr[i:i + line_len] for i in range(0, len(addr), line_len)]
    for i, ln in enumerate(lines[:3]):
        d.text((vx, 306 + i * 50), ln, font=val, fill=(20, 20, 20))

    d.text((lx, 530), "公民身份号码", font=lab, fill=(50, 50, 50))
    d.text((vx + 110, 524), rec["id_number"], font=_font(FONT_SONG, 34), fill=(20, 20, 40))

    # 照片占位
    d.rectangle([720, 110, 950, 420], fill=(225, 225, 230), outline=(180, 180, 180))
    d.text((760, 250), "照片", font=_font(FONT_HEI_L, 36), fill=(170, 170, 175))
    img.save(path, quality=95)


def render_back(rec, path: Path):
    W, H = 1010, 640
    img = Image.new("RGB", (W, H), (250, 250, 248))
    d = ImageDraw.Draw(img)
    # 国徽占位
    d.ellipse([90, 70, 230, 210], outline=(190, 60, 60), width=4)
    d.text((130, 120), "国徽", font=_font(FONT_HEI, 30), fill=(190, 60, 60))
    d.text((300, 110), "中华人民共和国", font=_font(FONT_HEI, 40), fill=(30, 30, 30))
    d.text((330, 175), "居民身份证", font=_font(FONT_HEI, 44), fill=(30, 30, 30))

    lab = _font(FONT_HEI_L, 30)
    val = _font(FONT_SONG, 32)
    d.text((110, 380), "签发机关", font=lab, fill=(40, 40, 40))
    d.text((350, 376), rec["register_org"], font=val, fill=(20, 20, 20))
    d.text((110, 470), "有效期限", font=lab, fill=(40, 40, 40))
    d.text((350, 466), rec["period_text"], font=val, fill=(20, 20, 20))
    img.save(path, quality=95)


def degrade(img_path: Path, kind: str, out_path: Path):
    img = Image.open(img_path).convert("RGB")
    if kind == "blur":
        img = img.filter(ImageFilter.GaussianBlur(1.3))
    elif kind == "rotate":
        img = img.rotate(-4, expand=True, fillcolor=(245, 245, 242))
    elif kind == "dark":
        img = ImageEnhance.Brightness(img).enhance(0.62)
    elif kind == "jpeg":
        tmp = out_path.with_suffix(".tmp.jpg")
        img.save(tmp, "JPEG", quality=30)
        img = Image.open(tmp).convert("RGB")
        tmp.unlink(missing_ok=True)
    elif kind == "small":
        w, h = img.size
        img = img.resize((w // 2, h // 2)).resize((w, h))
    img.save(out_path, quality=92)


def main(n=15, seed=20260618):
    random.seed(seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    variants = ["clean", "blur", "jpeg", "rotate", "dark", "small"]
    count = 0
    for i in range(n):
        front = make_front()
        back = make_back(front)
        for side, rec, render in (("front", front, render_front), ("back", back, render_back)):
            base = OUT_DIR / f"id_{i:02d}_{side}_clean.png"
            render(rec, base)
            for v in variants:
                out = OUT_DIR / f"id_{i:02d}_{side}_{v}.png"
                if v != "clean":
                    degrade(base, v, out)
                out.with_suffix(".json").write_text(
                    json.dumps({**rec, "variant": v}, ensure_ascii=False, indent=2))
                count += 1
    print(f"generated {count} id-card images for {n} persons -> {OUT_DIR}")


if __name__ == "__main__":
    main()
