"""Unit tests for parsers.py — 身份证正/反面解析与容错逻辑。

Run with either:
    python -m pytest test_parsers.py
    python test_parsers.py
"""

from parsers import _id_check_char, extract_fields


def _mkid(first17: str) -> str:
    return first17 + _id_check_char(first17)


def test_id_card_front_fields():
    code = _mkid("11010119900101001")
    f = extract_fields(
        "id_card_front",
        ["姓名 张三", f"公民身份号码 {code}", "住址 北京市朝阳区某街道"],
    )
    assert f["name"] == "张三"
    assert f["id_number"] == code
    assert f["address"] == "北京市朝阳区某街道"


def test_id_card_front_name_fallback_no_label():
    # 「姓名」标签整行丢失时，按版式兜底取顶部首个纯姓名行。
    f = extract_fields(
        "id_card_front",
        ["张三", "性别 男", "民族 汉", "住址 北京市朝阳区呼家楼街道东三环12号院3号楼"],
    )
    assert f["name"] == "张三"


def test_id_card_front_name_with_inner_space():
    f = extract_fields("id_card_front", ["姓名 张 三", "公民身份号码 11010119900101001X"])
    assert f["name"] == "张三"


def test_id_card_front_name_strips_merged_gender():
    f = extract_fields("id_card_front", ["姓名 张三性别 男", "住址 北京市朝阳区某街道"])
    assert f["name"] == "张三"


def test_id_card_front_name_strips_lone_xing():
    # 「性别」被截断只剩「性」粘到名字尾部。
    f = extract_fields("id_card_front", ["姓名 王小二性", "住址 北京市朝阳区某街道"])
    assert f["name"] == "王小二"


def test_id_card_front_id_letter_confusion():
    # 0 被误识为 O：号码位不允许字母，翻译回数字后校验通过。
    code = _mkid("11010119900101001")
    broken = "11" + "O" + code[3:]
    f = extract_fields("id_card_front", ["公民身份号码 " + broken])
    assert f["id_number"] == code


def test_id_card_front_id_digit_single_fix():
    # 出生日期段误识（日 01→81）使日期非法、校验位修复也过不了：
    # 唯一能让日期合法 + 校验通过的修正是把 8 纠回 0，即真值。
    code = _mkid("11010119901101001")  # 出生 1990-11-01
    broken = code[:12] + "8" + code[13:]
    f = extract_fields("id_card_front", ["公民身份号码 " + broken])
    assert f["id_number"] == code


def test_id_card_front_id_check_digit_fix():
    # 校验位本身误识：遍历 11 个合法校验码找回。
    code = _mkid("11010119900101001")
    broken = code[:17] + ("5" if code[17] != "5" else "6")
    f = extract_fields("id_card_front", ["公民身份号码 " + broken])
    assert f["id_number"] == code


def test_id_card_front_id_split_by_space():
    code = _mkid("11010119900101001")
    f = extract_fields("id_card_front", ["公民身份号码 " + code[:14] + " " + code[14:]])
    assert f["id_number"] == code


def test_id_card_front_id_no_label():
    # 标签丢失时按 18 位候选串全局兜底。
    code = _mkid("11010119900101001")
    f = extract_fields("id_card_front", ["姓名 张三", "住址 北京市朝阳区某街道", code])
    assert f["id_number"] == code


def test_id_card_front_address_keeps_juminqu():
    # 含「居民」的地址行（居民区/居委会）不能被水印过滤误删。
    f = extract_fields(
        "id_card_front",
        [
            "姓名 张三",
            "住址 云南省昆明市五华区幸福路",
            "12号居民区3号楼",
            "公民身份号码 11010119900101001X",
        ],
    )
    assert f["address"] == "云南省昆明市五华区幸福路12号居民区3号楼"


def test_id_card_front_id_best_effort_when_unfixable():
    # 校验不过且单点纠错无解时，仍返回翻译后的候选（best-effort，与老行为一致）。
    f = extract_fields("id_card_front", ["公民身份号码 99999999999999999O"])
    assert f["id_number"] == "999999999999999990"


def test_id_card_front_address_fallback_no_label():
    # 住址标签丢失时按地址形态兜底。
    f = extract_fields(
        "id_card_front",
        ["姓名 张三", "广东省广州市天河区天河路951号", "公民身份号码 11010119900101001X"],
    )
    assert f["address"] == "广东省广州市天河区天河路951号"


def test_id_card_back_range():
    f = extract_fields("id_card_back", ["有效期限 2018.05.01-2038.05.01"])
    assert f["is_long_term"] is False
    assert f["valid_from"] == "2018-05-01"
    assert f["expired_at"] == "2038-05-01"


def test_id_card_back_long_term():
    f = extract_fields("id_card_back", ["有效期限 2018.05.01-长期"])
    assert f["is_long_term"] is True
    assert f["expired_at"] == ""
    assert f["valid_from"] == "2018-05-01"


def test_id_card_back_no_label():
    # 国徽面除有效期限外无其它日期，标签丢失时全局兜底取区间。
    f = extract_fields("id_card_back", ["签发机关 昆明市公安局五华分局", "2018.05.01-2038.05.01"])
    assert f["valid_from"] == "2018-05-01"
    assert f["expired_at"] == "2038-05-01"


def test_id_card_back_long_term_no_label():
    f = extract_fields("id_card_back", ["签发机关 北京市公安局朝阳分局", "2018.05.01-长期"])
    assert f["is_long_term"] is True
    assert f["valid_from"] == "2018-05-01"


def test_id_card_back_label_split_line():
    f = extract_fields("id_card_back", ["有效期限", "2018.05.01-2038.05.01"])
    assert f["valid_from"] == "2018-05-01"
    assert f["expired_at"] == "2038-05-01"


def test_id_card_back_fullwidth_digits():
    # 翻拍图 OCR 偶发全角数字/全角分隔符。
    f = extract_fields("id_card_back", ["有效期限 ２０１８．０５．０１－２０３８．０５．０１"])
    assert f["valid_from"] == "2018-05-01"
    assert f["expired_at"] == "2038-05-01"


def test_id_card_back_letter_in_date():
    # 日期里 0 被误识为 O。
    f = extract_fields("id_card_back", ["有效期限 2O18.O5.O1-2O38.O5.O1"])
    assert f["valid_from"] == "2018-05-01"
    assert f["expired_at"] == "2038-05-01"


def test_id_card_back_date_before_label():
    # 日期行排在「有效期限」标签上一行（双栏顺序颠倒）：
    # 标签后只吃到「限」残片时必须回退全文。
    f = extract_fields(
        "id_card_back",
        ["签发机关 昆明市公安局五华分局", "2020.10.03-长期", "有效期限"],
    )
    assert f["is_long_term"] is True
    assert f["valid_from"] == "2020-10-03"


def test_id_card_back_spaced_date():
    # 翻拍件分隔符后带空格：「2019. 11. 11-2029. 11. 11」。
    f = extract_fields("id_card_back", ["有效期限", "2019. 11. 11-2029. 11. 11"])
    assert f["valid_from"] == "2019-11-11"
    assert f["expired_at"] == "2029-11-11"


def test_id_card_front_name_rejects_watermark_fragment():
    # 「姓名」下一行是误识的水印碎片「证电国」，不能当成姓名；
    # 真名「谢建国」在标签上方时应由兜底找回。
    f = extract_fields(
        "id_card_front",
        ["谢建国", "姓名", "证电国", "性别女", "民族", "维吾尔",
         "住址 上海市浦东新区张江镇科苑路83弄20号2室"],
    )
    assert f["name"] == "谢建国"


def test_unsupported_doc_type_returns_empty():
    # 营业执照等类型已下线：返回统一空字段而不是报错内容。
    f = extract_fields("business_license", ["名称 某某有限公司", "统一社会信用代码 94JURQ283FQEFLCR6M"])
    assert f["name"] == ""
    assert f["credit_code"] == ""


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
