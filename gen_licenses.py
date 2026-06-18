"""生成带「真值」的营业执照测试图片，用于评测 OCR 识别率。

设计目标：尽量贴近真实拍摄/扫描件，因此：
- 米黄底纹 + 斜向重复水印「SCJDGL」（会压在「名称」行上，复现真实难点）；
- 横版正本布局：统一社会信用代码 / 名称 / 类型 / 法定代表人 / 经营范围 / 注册资本 / 成立日期 / 住所 / 营业期限；
- 右下红色椭圆公章（半透明，叠在登记机关上）；
- 每个企业再派生「模糊 / 旋转 / JPEG 压缩 / 偏暗」等退化版本，模拟手机翻拍。

每张图同时写出同名 .json 真值，供 eval_ocr.py 比对。
"""

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = Path(__file__).parent / "test_images" / "generated"

# CJK 字体（macOS 自带）
FONT_HEI = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_SONG = "/System/Library/Fonts/Supplemental/Songti.ttc"

_CODE_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"  # 排除 I O Z S V
_CODE_INDEX = {c: i for i, c in enumerate(_CODE_CHARS)}
_CODE_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]

_SURNAMES = list("王李张刘陈杨黄赵周吴徐孙马朱胡郭何高林郑谢罗唐")
_GIVEN = ["伟", "芳", "娜", "敏", "静", "强", "磊", "军", "洋", "勇", "艳", "杰",
          "娟", "涛", "明", "超", "霞", "平", "刚", "桂英", "建国", "雪锋", "志强"]

_CITY = [
    ("北京市", "北京市朝阳区建国路{}号", "北京市市场监督管理局"),
    ("上海市", "上海市浦东新区世纪大道{}号", "上海市市场监督管理局"),
    ("广州市", "广东省广州市天河区天河路{}号", "广州市市场监督管理局"),
    ("深圳市", "广东省深圳市南山区科技中一路{}号", "深圳市市场监督管理局"),
    ("昆明市", "云南省昆明市五华区东风西路{}号", "昆明市市场监督管理局"),
    ("成都市", "四川省成都市武侯区人民南路{}段{}号", "成都市市场监督管理局"),
    ("杭州市", "浙江省杭州市西湖区文三路{}号", "杭州市市场监督管理局"),
]

_BRAND = ["蓝湾", "鼎盛", "宏远", "嘉禾", "金桥", "天成", "盛世", "锦绣", "弘业",
          "瑞丰", "华信", "众联", "卓越", "恒通", "万达", "禾屿", "星辰", "优品"]
_INDUSTRY = ["科技", "餐饮管理", "贸易", "信息技术", "文化传媒", "商贸", "食品",
             "电子商务", "建筑", "网络科技", "生物科技", "实业"]
_SUFFIX_COMPANY = ["有限公司", "有限责任公司", "（自然人独资）有限公司"]
_INDIV_SUFFIX = ["餐厅", "小吃店", "便利店", "餐饮店", "商行", "经营部", "超市"]

_TYPE_COMPANY = ["有限责任公司", "有限责任公司(自然人独资)", "有限责任公司(自然人投资或控股)"]
_SCOPE = [
    "餐饮服务；食品销售；预包装食品销售。",
    "技术开发、技术服务；软件开发；信息技术咨询服务。",
    "销售：日用百货、办公用品；货物进出口。",
    "餐饮管理；企业管理咨询；会议及展览服务。",
]


def _rand_name(person: bool):
    if person:
        suf = random.choice(_INDIV_SUFFIX)
        return f"{random.choice(_CITY)[0][:2]}市{random.choice(_BRAND)}{suf}"
    return f"{random.choice(_CITY)[0][:2]}{random.choice(_BRAND)}{random.choice(_INDUSTRY)}{random.choice(_SUFFIX_COMPANY)}"


def _rand_person():
    return random.choice(_SURNAMES) + random.choice(_GIVEN)


def _rand_code():
    # 生成带合法 GB32100 校验位的统一社会信用代码（首位 9 = 工商登记）。
    body = "9" + "".join(random.choice(_CODE_CHARS) for _ in range(16))
    total = sum(_CODE_INDEX[c] * w for c, w in zip(body, _CODE_WEIGHTS))
    check = _CODE_CHARS[(31 - (total % 31)) % 31]
    return body + check


def _rand_period():
    y = random.randint(2008, 2022)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    start = f"{y}年{m:02d}月{d:02d}日"
    iso_start = f"{y:04d}-{m:02d}-{d:02d}"
    if random.random() < 0.4:
        return f"{start}至长期", iso_start, "", True
    ey = y + random.choice([10, 20, 30])
    end = f"{ey}年{m:02d}月{d:02d}日"
    return f"{start}至{end}", iso_start, f"{ey:04d}-{m:02d}-{d:02d}", False


def make_record():
    person = random.random() < 0.35
    name = _rand_name(person)
    city = random.choice(_CITY)
    addr_tpl = city[1]
    addr = addr_tpl.format(*([random.randint(1, 999)] * addr_tpl.count("{}")))
    legal = _rand_person()
    code = _rand_code()
    period_text, vfrom, vto, longterm = _rand_period()
    ctype = random.choice(_INDIV_SUFFIX) if person else random.choice(_TYPE_COMPANY)
    return {
        "doc_type": "business_license",
        "name": name,
        "credit_code": code,
        "legal_person": legal,
        "address": addr,
        "type": ("个体工商户" if person else ctype),
        "scope": random.choice(_SCOPE),
        "capital": ("" if person else f"{random.choice([10,50,100,200,500,1000])}万元人民币"),
        "found_date": vfrom.replace("-", "年", 1).replace("-", "月") + "日",
        "period_text": period_text,
        "valid_from": vfrom,
        "expired_at": vto,
        "is_long_term": longterm,
        "register_org": city[2],
        "is_person": person,
    }


def _font(path, size):
    return ImageFont.truetype(path, size)


def render(rec, path: Path):
    W, H = 1500, 880
    img = Image.new("RGB", (W, H), (250, 247, 238))
    d = ImageDraw.Draw(img, "RGBA")

    # 斜向水印
    wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm)
    wf = _font(FONT_HEI, 40)
    for yy in range(-100, H + 100, 130):
        for xx in range(-100, W + 100, 360):
            wd.text((xx, yy), "SCJDGL", font=wf, fill=(120, 120, 120, 26))
    wm = wm.rotate(20, expand=False)
    img.paste(wm, (0, 0), wm)
    d = ImageDraw.Draw(img, "RGBA")

    # 边框
    d.rectangle([20, 20, W - 20, H - 20], outline=(150, 130, 90), width=3)

    title_f = _font(FONT_HEI, 64)
    d.text((W / 2 - 150, 70), "营 业 执 照", font=title_f, fill=(30, 30, 30))
    sub_f = _font(FONT_SONG, 22)
    d.text((W / 2 - 40, 150), "(副本)", font=sub_f, fill=(60, 60, 60))

    lab = _font(FONT_HEI, 24)
    val = _font(FONT_SONG, 25)

    # 统一社会信用代码
    d.text((90, 200), "统一社会信用代码", font=lab, fill=(40, 40, 40))
    d.text((360, 200), rec["credit_code"], font=_font(FONT_SONG, 27), fill=(20, 20, 20))

    left_x, val_x = 90, 240
    y = 270
    rows_left = [
        ("名　　称", rec["name"]),
        ("类　　型", rec["type"]),
        ("法定代表人" if not rec["is_person"] else "经 营 者", rec["legal_person"]),
        ("经营范围", rec["scope"]),
    ]
    for label, value in rows_left:
        d.text((left_x, y), label, font=lab, fill=(40, 40, 40))
        d.text((val_x, y), value, font=val, fill=(20, 20, 20))
        y += 60

    right_x, rval_x = 720, 870
    y = 270
    rows_right = [
        ("注册资本", rec["capital"]),
        ("成立日期", rec["found_date"]),
        ("营业期限", rec["period_text"]),
    ]
    for label, value in rows_right:
        if not value:
            continue
        d.text((right_x, y), label, font=lab, fill=(40, 40, 40))
        d.text((rval_x, y), value, font=val, fill=(20, 20, 20))
        y += 60

    # 住所（占整行）
    d.text((right_x, y + 10), "住　　所", font=lab, fill=(40, 40, 40))
    d.text((rval_x, y + 10), rec["address"], font=val, fill=(20, 20, 20))

    # 登记机关 + 公章
    d.text((720, 720), "登记机关", font=lab, fill=(40, 40, 40))
    d.text((870, 720), rec["register_org"], font=val, fill=(20, 20, 20))

    seal = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seal)
    sd.ellipse([10, 10, 230, 230], outline=(200, 30, 30, 150), width=5)
    sf = _font(FONT_HEI, 20)
    sd.text((45, 110), rec["register_org"][:6], font=sf, fill=(200, 30, 30, 150))
    sd.text((95, 30), "★", font=_font(FONT_HEI, 36), fill=(200, 30, 30, 160))
    img.paste(seal, (900, 600), seal)

    img.save(path, quality=95)


def degrade(img_path: Path, kind: str, out_path: Path):
    img = Image.open(img_path).convert("RGB")
    if kind == "blur":
        img = img.filter(ImageFilter.GaussianBlur(1.4))
    elif kind == "rotate":
        img = img.rotate(-4, expand=True, fillcolor=(245, 242, 233))
    elif kind == "dark":
        from PIL import ImageEnhance
        img = ImageEnhance.Brightness(img).enhance(0.62)
    elif kind == "jpeg":
        tmp = out_path.with_suffix(".tmp.jpg")
        img.save(tmp, "JPEG", quality=28)
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
    manifest = []
    for i in range(n):
        rec = make_record()
        base = OUT_DIR / f"lic_{i:02d}_clean.png"
        render(rec, base)
        for v in variants:
            out = OUT_DIR / f"lic_{i:02d}_{v}.png"
            if v != "clean":
                degrade(base, v, out)
            gt = out.with_suffix(".json")
            gt.write_text(json.dumps({**rec, "variant": v}, ensure_ascii=False, indent=2))
            manifest.append(str(out.name))
    print(f"generated {len(manifest)} images for {n} companies -> {OUT_DIR}")


if __name__ == "__main__":
    main()
