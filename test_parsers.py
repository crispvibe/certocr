"""Unit tests for ocr-service/parsers.py — covers the 长期 / expiry-date logic.

Run with either:
    python -m pytest ocr-service/test_parsers.py
    python ocr-service/test_parsers.py
"""

from parsers import extract_fields


def test_business_license_at_long_term():
    # "至 长期" must NOT write the start date into expired_at (the core bug).
    f = extract_fields("business_license", ["营业期限 2015年3月12日 至 长期"])
    assert f["is_long_term"] is True
    assert f["expired_at"] == ""
    assert f["valid_from"] == "2015-03-12"


def test_business_license_two_date_range():
    f = extract_fields(
        "business_license", ["营业期限：2015年3月12日 至 2035年3月12日"]
    )
    assert f["is_long_term"] is False
    assert f["valid_from"] == "2015-03-12"
    assert f["expired_at"] == "2035-03-12"


def test_business_license_single_end_date():
    # A lone date AFTER the 至 separator is the expiry.
    f = extract_fields("business_license", ["有效期 至 2035-03-12"])
    assert f["is_long_term"] is False
    assert f["expired_at"] == "2035-03-12"


def test_business_license_no_period_keyword_no_guess():
    # Without a 营业期限/经营期限/有效期 anchor we must NOT grab a stray date
    # (e.g. the registration / issue date at the bottom of the document).
    f = extract_fields(
        "business_license", ["登记机关 北京市市场监督管理局", "2020年1月1日"]
    )
    assert f["expired_at"] == ""
    assert f["is_long_term"] is False


def test_business_license_name_with_label():
    f = extract_fields(
        "business_license",
        ["名称 昆明蓝湾科技有限公司", "类型 有限责任公司（自然人独资）"],
    )
    assert f["name"] == "昆明蓝湾科技有限公司"


def test_business_license_name_suffix_fallback():
    # OCR 未读到「名称」标签时，按公司后缀兜底；不可把「类型」值当成名称。
    f = extract_fields(
        "business_license",
        [
            "统一社会信用代码 91530102MAE9601W1Q",
            "型有限责任公司（自然人独资）",
            "昆明蓝湾科技有限公司",
            "成立日期2025年01月22日",
            "法定代表人 张雪锋",
        ],
    )
    assert f["name"] == "昆明蓝湾科技有限公司"


def test_business_license_type_not_used_as_name():
    # 只有「类型」行、没有真实名称时，名称应为空而不是「有限责任公司（自然人独资）」。
    f = extract_fields(
        "business_license",
        ["型有限责任公司（自然人独资）", "成立日期2025年01月22日"],
    )
    assert f["name"] == ""


def test_business_license_founding_date_not_expiry():
    # 仅有「成立日期」、无「营业期限」关键字时，不得把成立日期写进 expired_at。
    f = extract_fields(
        "business_license",
        ["成立日期2025年01月22日", "住所 云南省昆明市五华区"],
    )
    assert f["expired_at"] == ""
    assert f["valid_from"] == ""
    assert f["is_long_term"] is False


def test_business_license_individual_household():
    f = extract_fields(
        "business_license",
        ["名称 张三餐饮店", "经营者 张三"],
    )
    assert f["name"] == "张三餐饮店"


def test_business_license_individual_operator():
    # 个体工商户照面用「经营者」，应能填入 legal_person。
    f = extract_fields(
        "business_license",
        ["名称 北京市弘业餐厅", "类型 个体工商户", "经营者", "孙勇"],
    )
    assert f["legal_person"] == "孙勇"


def test_business_license_legal_person_split_label():
    # 双栏竖排把「负责人」拆成「负」「责人」、姓名落到下一行时应兜底补齐。
    f = extract_fields(
        "business_license",
        ["名称 某某分公司", "负", "责人", "覃小花", "成立日期2016年12月09日"],
    )
    assert f["legal_person"] == "覃小花"


def test_business_license_legal_person_not_label_word():
    # 标签残片下一行若仍是标签词（如「经营者」），不得误当成姓名。
    f = extract_fields(
        "business_license",
        ["经营者", "个人经营", "注册日期 2004年11月01日"],
    )
    assert f["legal_person"] == ""


def test_business_license_credit_code_valid_passthrough():
    # 校验位合法的代码直接采用。
    f = extract_fields("business_license", ["94JURQ283FQEFLCR6M"])
    assert f["credit_code"] == "94JURQ283FQEFLCR6M"


def test_business_license_credit_code_check_digit_fix():
    # 8 被误识成禁用字符 S 时，用 GB32100 校验位反推纠回。
    f = extract_fields("business_license", ["94JURQ2S3FQEFLCR6M"])
    assert f["credit_code"] == "94JURQ283FQEFLCR6M"


def test_business_license_credit_code_prefers_valid_candidate():
    # 同图多候选（双通道）时，优先采用校验位合法的那个。
    f = extract_fields(
        "business_license",
        ["94JURQ2S3FQEFLCR6M", "94JURQ283FQEFLCR6M"],
    )
    assert f["credit_code"] == "94JURQ283FQEFLCR6M"


def test_business_license_credit_code_safe_letter_fix():
    # 不含禁用字符但校验不过时不乱猜；仅含 O/I/Z 时退回安全替换。
    f = extract_fields("business_license", ["91O102MAE96O1W1ZQ7"])
    assert "O" not in f["credit_code"] and "I" not in f["credit_code"]


def test_business_license_name_strips_trailing_label():
    # 双栏布局把右栏标签粘到名称尾部时应剥离。
    f = extract_fields(
        "business_license",
        ["名", "称", "深圳卓越餐饮管理（自然人独资）有限公司注册资本"],
    )
    assert f["name"] == "深圳卓越餐饮管理（自然人独资）有限公司"


def test_business_license_address_fallback_skips_watermark():
    # 「住所」后紧跟的是水印片段时，应按地址形态兜底挑出真实地址行。
    f = extract_fields(
        "business_license",
        ["住所", "JDGI", "广东省广州市天河区天河路951号", "广州市市场监督管理局"],
    )
    assert f["address"] == "广东省广州市天河区天河路951号"


def test_business_license_address_multiline_join():
    # 双栏布局把「住所」标签与地址值拆行，且地址跨两行；应多行拼接。
    f = extract_fields(
        "business_license",
        ["住", "所", "云南省昆明市五华区人民中路", "238号华尔顿大厦5楼501室"],
    )
    assert f["address"] == "云南省昆明市五华区人民中路238号华尔顿大厦5楼501室"


def test_business_license_address_county_without_province():
    # 少数地址直接以「X县」开头（无省/市），带街路+门牌号时应兜底采信。
    f = extract_fields(
        "business_license",
        ["名称 山西新达科技股份有限公司", "住所", "闻喜县太风西路149号"],
    )
    assert f["address"] == "闻喜县太风西路149号"


def test_business_license_address_guess_rejects_comma_noise():
    # 标签丢失时按形态兜底；含逗号的串行噪声（多字段连成一行）不应被采信。
    f = extract_fields(
        "business_license",
        ["名称 某某有限公司", "厂庆阳县城客达政联，二级公路脂城线以北地度2号地，川9，30号"],
    )
    assert f["address"] == ""


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


def test_id_card_front_fields():
    f = extract_fields(
        "id_card_front",
        ["姓名 张三", "公民身份号码 11010119900101001X", "住址 北京市朝阳区某街道"],
    )
    assert f["name"] == "张三"
    assert f["id_number"] == "11010119900101001X"
    assert f["address"] == "北京市朝阳区某街道"


def test_food_license_expiry():
    f = extract_fields("food_license", ["有效期至 2026年5月1日"])
    assert f["is_long_term"] is False
    assert f["expired_at"] == "2026-05-01"


def test_food_license_long_term():
    f = extract_fields("food_license", ["有效期至 长期"])
    assert f["is_long_term"] is True
    assert f["expired_at"] == ""


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
