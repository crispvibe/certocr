import re
from datetime import datetime
from typing import Any

_LONG_TERM_KEYWORDS = ("长期", "长年", "永久")

# 营业执照「名称」常见后缀，用于在 OCR 未读到「名称」标签时按行兜底提取商户名称。
_COMPANY_NAME_SUFFIXES = (
    "有限公司",
    "有限责任公司",
    "股份有限公司",
    "公司",
    "合伙企业",
    "个体工商户",
    "经营部",
    "服务部",
    "商行",
    "商店",
    "商贸行",
    "合作社",
    "中心",
    "事务所",
    "工作室",
    "工程队",
    "餐厅",
    "酒店",
    "酒楼",
    "饭店",
    "餐饮店",
    "超市",
    "便利店",
    "门市部",
    "经销处",
    "厂",
    "店",
)

# 行内若含这些词，说明是「类型/经营范围/成立日期」等非名称行，名称兜底时跳过。
_NAME_EXCLUDE_KEYWORDS = (
    "类型",
    "经营范围",
    "成立日期",
    "注册资本",
    "登记机关",
    "统一社会信用",
    "信用代码",
    "营业执照",
    "法定代表",
    "负责人",
    "经营者",
    "住所",
    "地址",
    "营业期限",
    "经营期限",
    "有效期",
)


def _guess_company_name(lines: list[str]) -> str:
    """OCR 未读到「名称」标签时，按公司后缀兜底提取商户名称。

    仅当行以公司后缀结尾、长度合理且不含「类型/经营范围」等干扰词时才采用，
    避免把「有限责任公司（自然人独资）」这类「类型」值误当作名称。
    """
    for raw in lines:
        ln = (raw or "").strip()
        if not (3 < len(ln) <= 40):
            continue
        if any(kw in ln for kw in _NAME_EXCLUDE_KEYWORDS):
            continue
        # 类型值常形如「型有限责任公司（自然人独资）」，以「型」开头或以括号结尾，排除。
        if ln.startswith(("型", "（", "(")):
            continue
        if ln.endswith(("）", ")")):
            continue
        if ln.endswith(_COMPANY_NAME_SUFFIXES):
            return ln
    return ""


# 住所/经营场所 标签的各种写法（含分支机构的「营业场所/经营场所」）。
# 注意：常量统一加 _BL_ 前缀，避免与下方身份证解析复用的 _ADDR_* 同名被覆盖。
_BL_ADDR_LABELS = (
    "住所", "住址", "经营场所", "营业场所", "生产经营场所", "主要经营场所", "地址",
)
# 「强地址标记」：出现这些字才认为某行（或续行）确实是地址，避免把页脚提示语
# （如「市场主体应当于每年1月1日至6月30日…」）当成住所拼进来。
_BL_ADDR_MARK = re.compile(
    r"[省市区县镇乡村路街巷弄号室幢栋楼苑园社道厦场寓]|工业|大道|开发区|科技馆"
)
# 命中这些词说明该行属于其它字段或页脚正文，地址拼接到此为止。
_BL_ADDR_STOP = (
    "注册资本", "成立日期", "法定代表", "经营范围", "登记机关", "类型", "名称",
    "统一社会信用", "信用代码", "负责人", "经营者", "注册号", "营业期限",
    "经营期限", "有效期", "公积金", "二维码", "市场监督", "工商行政",
    "市场主体", "应当", "公示", "年报", "报送", "提示", "网址", "义务",
    "登记日期", "扫描", "国家企业", "中华人民", "gsxt", "http", "www", "成立",
)
# 仅为标签残片、应跳过的整行。
_BL_ADDR_FRAGMENT = {"住", "所", "址", "住所", "住址", "经营场所", "营业场所", "场所"}
# 续行/取值时需剥除的前导标签残片。
_BL_ADDR_PREFIX = re.compile(r"^[\s:：]*(?:住所|住址|经营场所|营业场所|地址|住|所|址)?[\s:：]*")


def _bl_addr_value(ln: str):
    """若某行带地址标签，返回标签后的值（可能为空字符串）；否则返回 None。"""
    for lab in _BL_ADDR_LABELS:
        spaced = r"\s*".join(lab)  # 允许「住　所」被空格拆开
        m = re.match(rf"^\s*{spaced}\s*[:：]?\s*(.*)$", ln)
        if m:
            return m.group(1).strip()
    # 双栏布局里 OCR 常把「住」「所」拆行，只剩「所」打头再接地址值。
    m = re.match(r"^\s*[住]?所\s*[:：]?\s*(.*)$", ln)
    if m and (m.group(1) == "" or _BL_ADDR_MARK.search(m.group(1))):
        return m.group(1).strip()
    return None


def _find_address(lines: list[str]) -> str:
    """逐行定位地址标签并拼接续行，兼容两栏布局/换行/「营业场所」等写法。

    续行严格要求含强地址标记且非页脚正文，防止把年报提示语误拼为住所。
    """
    n = len(lines)
    for i, raw in enumerate(lines):
        ln = (raw or "").strip()
        val = _bl_addr_value(ln)
        if val is None:
            continue
        val = _BL_ADDR_PREFIX.sub("", val).strip()
        parts = [val] if val else []
        j = i + 1
        while j < n:
            nxt = (lines[j] or "").strip()
            if not nxt or nxt in _BL_ADDR_FRAGMENT:
                j += 1
                continue
            if any(s in nxt for s in _BL_ADDR_STOP):
                break
            cleaned = _BL_ADDR_PREFIX.sub("", nxt).strip()
            if 0 < len(cleaned) <= 40 and _BL_ADDR_MARK.search(cleaned):
                parts.append(cleaned)
                j += 1
                if re.search(r"[室号幢栋楼]\s*$", cleaned):
                    break
                continue
            break
        addr = "".join(parts).strip(" :：")
        if len(addr) >= 6 and _BL_ADDR_MARK.search(addr):
            return addr
    return ""


# 身份证「住址」常换 2~3 行，OCR 拆成多行；按地址用字向下拼接。
_ADDR_KEYWORDS = tuple("省市区县乡镇街道路弄号栋幢室单元楼组村社区院巷道街村委")
_ADDR_STOP = ("公民身份", "身份号码", "签发", "有效期")
_ADDR_SKIP = ("姓名", "姓 名", "性别", "民族", "出生", "CHINA", "中国",
              "居民身份证", "照片", "中华人民共和国")


def _id_front_address(lines: list[str]) -> str:
    label_idx = -1
    inline = ""
    for i, raw in enumerate(lines):
        m = re.search(r"(?:住\s*址|地\s*址)[:：]?\s*(.*)", raw or "")
        if m:
            label_idx = i
            inline = m.group(1).strip()
            break
    if label_idx < 0:
        return ""
    parts = [inline] if inline else []
    for raw in lines[label_idx + 1:]:
        s = (raw or "").strip()
        if not s:
            continue
        if any(k in s for k in _ADDR_STOP) or re.search(r"\d{15,}", s):
            break
        if any(k in s for k in _ADDR_SKIP):
            continue
        if any(k in s for k in _ADDR_KEYWORDS) or len(re.findall(r"[\u4e00-\u9fa5]", s)) >= 3:
            parts.append(s)
        else:
            break
    return "".join(parts).strip()


_ADDR_REGION = ("省", "市", "自治区", "特别行政区")
_ADDR_UNIT = tuple("路街号弄栋幢室区县镇乡村组院巷道段大厦广场")
_ADDR_NOISE = ("市场监督", "监督管理", "登记机关", "营业执照", "经营范围",
               "SCJDGL", "JDGL", "JDGI", "信用代码", "名称", "类型")


def _looks_like_address(s: str) -> bool:
    s = (s or "").strip()
    if len(s) < 8:
        return False
    if any(n in s for n in _ADDR_NOISE):
        return False
    # 干净的注册地址一般不含逗号/分号；含则多为 OCR 串行噪声（把多字段连成一行），拒绝。
    if re.search(r"[，、；,;]", s):
        return False
    # 标准形态：含省/市/自治区/特别行政区 + 路/号/室 等门牌单位字。
    if any(r in s for r in _ADDR_REGION) and any(u in s for u in _ADDR_UNIT):
        return True
    # 兜底：少数地址直接以「X县」开头（无省市），须同时带街/路/道 + 门牌号方可采信。
    if "县" in s[:6] and any(u in s for u in ("路", "街", "道", "号", "巷")) and re.search(r"\d", s):
        return True
    return False


def _guess_address(lines: list[str]) -> str:
    """标签匹配失败时，按地址形态兜底挑「最完整的地址行」。

    营业执照「住所」常因双栏/水印导致标签与值不相邻，OCR 偶把水印片段
    （SCJDGL→JDGI）接到「住所」后；此处直接按地址特征择最长行，绕开标签。
    """
    candidates = [ln.strip() for ln in lines if _looks_like_address(ln)]
    return max(candidates, key=len) if candidates else ""


# 法定代表人/负责人/经营者 标签在双栏竖排时常被 OCR 拆字换行（如「负」「责人」），
# 名字落到标签行的下一行；下面按「标签残片结尾行 + 紧邻纯姓名行」兜底。
_LP_LABEL_TAIL = re.compile(r"(?:法定代表人|负责人|经营者|投资人|责人|代表人)\s*[:：]?\s*$")
_LP_NAME = re.compile(r"^[\u4e00-\u9fa5·]{2,8}$")
# 姓名行排除词：相邻字段值/标签残片，避免把「经营者」「个人经营」等当成姓名。
_LP_NAME_STOP = (
    "有限", "公司", "责任", "企业", "经营", "范围", "注册", "资本", "成立",
    "日期", "住所", "场所", "类型", "名称", "机关", "信用", "代码", "期限",
    "组成", "形式", "股东", "出资", "负责", "代表", "营者", "投资", "个人",
)


def _find_legal_person(lines: list[str]) -> str:
    """标签与姓名被竖排拆行时的兜底：定位标签残片结尾行，取其下首个纯姓名行。"""
    n = len(lines)
    for i, raw in enumerate(lines):
        ln = (raw or "").strip()
        if not _LP_LABEL_TAIL.search(ln):
            continue
        for j in range(i + 1, min(i + 4, n)):
            nxt = (lines[j] or "").strip()
            if not nxt:
                continue
            if _LP_NAME.match(nxt) and not any(k in nxt for k in _LP_NAME_STOP):
                return nxt
            break
    return ""


def _is_long_term(text: str) -> bool:
    return any(kw in text for kw in _LONG_TERM_KEYWORDS)


def _normalize_date(text: str) -> str:
    text = text.strip()
    if not text or _is_long_term(text):
        return ""
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace(".", "-").replace("/", "-")
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if not m:
        return ""
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _join_text(lines: list[str]) -> str:
    return "\n".join([x.strip() for x in lines if x and x.strip()])


# 完整营业期限区间：日期 至 日期 / 日期 至 长期。两侧均要求带 4 位年份，
# 以避开「每年1月1日至6月30日」这类年报提示语的误命中。
_PERIOD_RANGE = re.compile(
    r"(\d{4}[年./\-]\d{1,2}[月./\-]\d{1,2}日?)\s*[至到\-—~]+\s*"
    r"(长期|长年|永久|\d{4}[年./\-]\d{1,2}[月./\-]\d{1,2}日?)"
)


def _find_dates(text: str) -> list[str]:
    patterns = [
        r"\d{4}年\d{1,2}月\d{1,2}日",
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}",
    ]
    found: list[str] = []
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            normalized = _normalize_date(m.group(0))
            if normalized and normalized not in found:
                found.append(normalized)
    return found


import itertools

# 统一社会信用代码（GB 32100）字符集：不含 I/O/Z/S/V，共 31 个字符。
_CC_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"
_CC_INDEX = {c: i for i, c in enumerate(_CC_CHARS)}
_CC_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]
_CC_FORBIDDEN = set("IOZSV")
# 明确、低风险的字母→数字纠正（仅形近且不可能出现的字母）。
_CC_SAFE_FIX = {"I": "1", "O": "0", "Z": "2"}
# OCR 形近混淆表：观测字符 -> 可能的真实字符（仅列入合法字符集者）。
# 用于校验位反推纠错，重点覆盖禁用字符（I/O/Z/S/V，必为误识）。
_CC_CONFUSE = {
    "S": ["8", "5", "6"],
    "O": ["0", "D", "Q"],
    "I": ["1"],
    "Z": ["2", "7"],
    "V": ["Y", "U"],
    "B": ["8"],
    "D": ["0"],
    "G": ["6", "9"],
    "Q": ["0"],
    "L": ["1"],
    "0": ["D", "Q"],
    "8": ["B"],
}


def _cc_check_char(first17: str) -> str:
    total = sum(_CC_INDEX[c] * w for c, w in zip(first17, _CC_WEIGHTS))
    return _CC_CHARS[(31 - (total % 31)) % 31]


def _cc_valid(code: str) -> bool:
    if len(code) != 18 or any(c not in _CC_INDEX for c in code):
        return False
    return _cc_check_char(code[:17]) == code[17]


def _cc_correct(code: str) -> str:
    """用 GB32100 校验位反推纠错（高精度策略）。

    只在「禁用字符位（I/O/Z/S/V）」上按形近表替换——这些位必为 OCR 误识，
    搜索空间小且几乎不会误纠。若不含禁用字符却校验不过（可能是合法位上的
    其它误识，无法可靠定位），不做猜测，返回空串交由上层兜底。
    """
    if len(code) != 18 or not any(ch in _CC_FORBIDDEN for ch in code):
        return ""
    opts = []
    for ch in code:
        if ch in _CC_FORBIDDEN:
            opts.append([a for a in _CC_CONFUSE.get(ch, ["0"]) if a in _CC_INDEX] or ["0"])
        else:
            opts.append([ch])
    total = 1
    for o in opts:
        total *= len(o)
    if total > 20000:
        return ""
    for combo in itertools.product(*opts):
        cand = "".join(combo)
        if _cc_valid(cand):
            return cand
    return ""


def _find_credit_code(text: str) -> str:
    candidates = re.findall(r"[0-9A-Z]{18}", text.upper())
    if not candidates:
        return ""
    # 1) 若有候选直接通过 GB32100 校验，最可信，直接采用。
    for c in candidates:
        if _cc_valid(c):
            return c
    # 2) 选含禁用字符最少者做校验位反推纠错（双通道择优 + 纠错）。
    best = min(candidates, key=lambda c: sum(ch in _CC_FORBIDDEN for ch in c))
    fixed = _cc_correct(best)
    if fixed:
        return fixed
    # 3) 兜底：仅做最安全的字母→数字替换。
    return "".join(_CC_SAFE_FIX.get(ch, ch) for ch in best)


def extract_fields(doc_type: str, lines: list[str]) -> dict[str, Any]:
    text = _join_text(lines)
    fields: dict[str, Any] = {
        "name": "",
        "address": "",
        "legal_person": "",
        "credit_code": "",
        "id_number": "",
        "expired_at": "",
        "valid_from": "",
        "valid_to": "",
        "is_long_term": False,
    }
    if not text:
        return fields

    if doc_type == "business_license":
        fields["credit_code"] = _find_credit_code(text)
        m = re.search(r"(?:名\s*称|名称)[:：]?\s*([^\n]+)", text)
        if m:
            fields["name"] = m.group(1).strip()
        # 1) 首选多行/容错拼接：兼容双栏布局把「住所」标签与值拆行、地址跨 2~3
        #    行换行的情况，比单行正则更稳，故提到最高优先级。
        fields["address"] = _find_address(lines)
        # 2) 多行拼接失败时，退回「同行标签取值」，并要求像地址才采用。
        if not fields["address"]:
            m = re.search(r"(?:住\s*所|住所|地\s*址)[:：]?\s*([^\n]+)", text)
            if m and _looks_like_address(m.group(1)):
                fields["address"] = m.group(1).strip()
        # 3) 仍失败（标签丢失/取到水印片段）时，按地址形态全局兜底择最长行。
        if not fields["address"]:
            fields["address"] = _guess_address(lines)
        for pattern in (
            r"法定代表人\s*([\u4e00-\u9fa5·]{2,8})",
            # 个体工商户照面用「经营者」，公司/分支用「负责人」。
            r"(?:法定代表|负责人|经营者)[:：]?\s*([\u4e00-\u9fa5·]{2,8})",
        ):
            m = re.search(pattern, text)
            if m:
                cand = m.group(1).strip()
                # 正则的 \s* 会跨行，故可能误吞下一行的字段值（如「经营者」后接
                # 「个人经营」这类组成形式），含相邻字段/标签词的一律弃用。
                if not any(k in cand for k in _LP_NAME_STOP):
                    fields["legal_person"] = cand
                    break
        # 兜底：双栏竖排把「负责人/经营者」标签与姓名拆行时，按相邻行补齐。
        if not fields["legal_person"]:
            fields["legal_person"] = _find_legal_person(lines)
        m = re.search(
            r"(?:名\s*称|名称)[:：]?\s*([^\n]{2,40}?)(?:\n|类型|法定代表)",
            text,
        )
        if m and not fields["name"]:
            fields["name"] = m.group(1).strip()
        if not fields["name"]:
            fields["name"] = _guess_company_name(lines)
        # 双栏布局下 OCR 常把右栏标签并入「名称」行（如「…有限公司注册资本」），
        # 去掉名称尾部粘连的相邻字段标签。
        if fields["name"]:
            fields["name"] = re.sub(
                r"(?:注册资本|成立日期|营业期限|经营期限|类\s*型|法定代表人?|经营者|登记机关|住\s*所|经营范围).*$",
                "",
                fields["name"],
            ).strip()
        period = re.search(
            r"(?:营业期限|经营期限|有效期)[:：]?\s*([^\n]+)", text
        )
        if period:
            period_text = period.group(1)
            period_dates = _find_dates(period_text)
            if _is_long_term(period_text):
                fields["is_long_term"] = True
                if period_dates:
                    fields["valid_from"] = period_dates[0]
            elif len(period_dates) >= 2:
                fields["valid_from"] = period_dates[0]
                fields["expired_at"] = period_dates[-1]
            elif len(period_dates) == 1:
                # Only one date in the 营业期限. Decide start vs end by its
                # position relative to the 至/到 separator: "2015年3月12日 至 长期"
                # has the date BEFORE 至, so it is the start (valid_from). Never
                # assume a lone start date is the expiry — that was the core bug.
                sep = re.search(r"[至到\-—~]", period_text)
                date_pos = re.search(r"\d{4}", period_text)
                if sep and date_pos and date_pos.start() > sep.start():
                    fields["expired_at"] = period_dates[0]
                else:
                    fields["valid_from"] = period_dates[0]
        # 兜底：两栏布局里 OCR 常把「营业期限」标签和日期拆成两行，导致上面按
        # 标签同行取值失败。此时全局扫描「日期 至 日期/长期」区间补齐。
        if not fields["valid_from"] and not fields["expired_at"] and not fields["is_long_term"]:
            mrange = _PERIOD_RANGE.search(text)
            if mrange:
                fields["valid_from"] = _normalize_date(mrange.group(1))
                tail = mrange.group(2)
                if _is_long_term(tail):
                    fields["is_long_term"] = True
                else:
                    fields["expired_at"] = _normalize_date(tail)
        return fields

    if doc_type == "id_card_front":
        # 身份证正面底纹常含「中国 CHINA 居民身份证」水印，CLAHE 增强后易被 OCR 读出，
        # 倾斜件尤甚，会污染「姓名」。先剔除水印行（不含正面合法字段，安全）。
        wm = ("居民身份证", "身份证", "份证", "CHINA", "中国", "居民")
        lines = [ln for ln in lines if not any(w in (ln or "") for w in wm)]
        text = _join_text(lines)
        m = re.search(r"(?:姓名|姓\s*名)[:：]?\s*([\u4e00-\u9fa5·]{2,8})", text)
        if m:
            # 姓名常与「性别」同处理误并入，去掉尾部紧跟的标签字。
            fields["name"] = re.sub(r"(?:性别|民族|出生).*$", "", m.group(1)).strip()
        addr = _id_front_address(lines)
        if addr:
            fields["address"] = addr
        else:
            m = re.search(r"(?:住址|地址)[:：]?\s*([^\n]+)", text)
            if m:
                fields["address"] = m.group(1).strip()
        # 身份证号 18 位（末位可能为 X）；OCR 偶把 X 读成 x 已 upper 兜底。
        m = re.search(r"(?:公民身份号码|身份证号码?|号码)[:：]?\s*([0-9Xx]{18})", text)
        if not m:
            m = re.search(r"\b(\d{17}[0-9Xx])\b", text)
        if m:
            fields["id_number"] = m.group(1).upper()
        return fields

    if doc_type == "id_card_back":
        if _is_long_term(text):
            fields["is_long_term"] = True
            m = re.search(
                r"(?:有效期限?)[:：]?\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
                text,
            )
            if m:
                fields["valid_from"] = _normalize_date(m.group(1))
            return fields
        m = re.search(
            r"(?:有效期限)[:：]?\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)\s*[-—至到]+\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
            text,
        )
        if m:
            fields["valid_from"] = _normalize_date(m.group(1))
            fields["expired_at"] = _normalize_date(m.group(2))
        return fields

    if doc_type == "food_license":
        m = re.search(r"(?:经营者名称|单位名称|名称)[:：]?\s*([^\n]+)", text)
        if m:
            fields["name"] = m.group(1).strip()
        m = re.search(r"(?:住所|地址|经营场所)[:：]?\s*([^\n]+)", text)
        if m:
            fields["address"] = m.group(1).strip()
        m = re.search(r"(?:法定代表人|负责人)[:：]?\s*([\u4e00-\u9fa5·]{2,8})", text)
        if m:
            fields["legal_person"] = m.group(1).strip()
        m = re.search(r"(?:有效期至|有效期限至|至)\s*[:：]?\s*([^\n]+)", text)
        if m:
            tail = m.group(1)
            if _is_long_term(tail):
                fields["is_long_term"] = True
            else:
                d = _find_dates(tail)
                if d:
                    fields["expired_at"] = d[-1]
        return fields

    return fields
