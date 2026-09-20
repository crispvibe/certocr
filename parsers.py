import re
from datetime import datetime
from typing import Any

_LONG_TERM_KEYWORDS = ("长期", "长年", "永久")

# 常见证照 OCR 误识纠正（多字词级，命中即整体替换）。
# 只收录「几乎不可能是正确文本」的词，避免误伤合法名称/地址。后续可继续追加。
_OCR_PHRASE_FIXES = {
    "白由贸易": "自由贸易",  # 自 被误识为 白（自由贸易试验区）
}


def _fix_common_ocr_typos(s: str) -> str:
    if not s:
        return s
    for wrong, right in _OCR_PHRASE_FIXES.items():
        if wrong in s:
            s = s.replace(wrong, right)
    return s


# 数字上下文内的形近字符归一化：全角数字、日期里常见的字母误识、全角分隔符。
# 只用于日期/号码等「只能是数字」的局部文本，不会改伤正文汉字。
_NUM_FIX = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "I": "1", "l": "1", "|": "1",
    "Z": "2", "z": "2",
    "S": "5", "s": "5",
    "G": "6",
    "B": "8",
    "g": "9", "q": "9",
    "!": "1", "b": "6",
    "．": ".", "。": ".",
    "－": "-", "–": "-", "—": "-", "―": "-", "﹣": "-",
    "～": "~", "﹕": ":", "：": ":",
})


def _fix_num(text: str) -> str:
    return (text or "").translate(_NUM_FIX)


def _is_long_term(text: str) -> bool:
    return any(kw in text for kw in _LONG_TERM_KEYWORDS)


def _normalize_date(text: str) -> str:
    # OCR 常在分隔符后插空格（「2019. 11. 11」），先去掉空白再解析。
    text = re.sub(r"\s+", "", _fix_num(text))
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


def _find_dates(text: str) -> list[str]:
    text = _fix_num(text)
    found: list[str] = []
    # 分隔符之间允许空白（翻拍件 OCR 常读成「2019. 11. 11」）。
    for m in re.finditer(
        r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,2}",
        text,
    ):
        normalized = _normalize_date(m.group(0))
        if normalized and normalized not in found:
            found.append(normalized)
    return found


# ---------------------------------------------------------------------------
# 公民身份号码：18 位 = 6 位区划 + 8 位出生日期 + 3 位顺序 + 1 位校验码（ISO 7064 MOD 11-2）
# ---------------------------------------------------------------------------
_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK = "10X98765432"
_ID_CHECK_CHARS = "0123456789X"
# 号码位只允许数字+X，字母出现在号码位必为 OCR 形近误识，经 _NUM_FIX 安全替换。
# 校验失败时单点纠错的形近数字候选（观测字符 -> 可能的真实字符）。
_ID_DIGIT_ALT = {
    "0": ["8", "6", "9"],
    "1": ["7", "2"],
    "2": ["1", "7"],
    "3": ["8", "5", "9"],
    "4": ["9", "7"],
    "5": ["6", "8", "3"],
    "6": ["0", "5", "8", "9"],
    "7": ["1", "2"],
    "8": ["0", "6", "3"],
    "9": ["7", "4", "0", "8"],
}
# 号码候选宽松字符集：数字 + 常见误识字母（号码上下文里这些字母不可能合法）。
_ID_LOOSE = r"[0-9OQoDilI|!ZzSsGbBgq]"


def _id_check_char(first17: str) -> str:
    s = sum(int(c) * w for c, w in zip(first17, _ID_WEIGHTS))
    return _ID_CHECK[s % 11]


def _id_birth_ok(code: str) -> bool:
    """号码 7~14 位必须构成合法出生日期，作为纠错结果的交叉验证。"""
    try:
        y = int(code[6:10])
        datetime(y, int(code[10:12]), int(code[12:14]))
    except ValueError:
        return False
    return 1900 <= y <= datetime.now().year


def _id_ok(code: str) -> bool:
    return (
        len(code) == 18
        and code[:17].isdigit()
        and code[17] in _ID_CHECK_CHARS
        and _id_birth_ok(code)
        and _id_check_char(code[:17]) == code[17]
    )


def _correct_id_number(code: str) -> str:
    """校验失败时的单点纠错，两级收敛：

    1) 先试末位校验码：校验位不含信息量（区划+出生+顺序才是数据），单字符误识
       落在校验位上时，直接换成正确校验码即可保留全部 17 个数据位原样。
    2) 校验位修复仍不过，说明误识位大概率在出生日期段（日期不合法会连带使
       第 1 步失败）——此时逐位试形近数字替换；能同时让「出生日期合法 +
       校验位通过」的替换基本唯一，误纠概率极低。
    """
    if len(code) != 18 or not code[:17].isdigit() or code[17] not in _ID_CHECK_CHARS:
        return ""
    for c in _ID_CHECK_CHARS:
        if _id_ok(code[:17] + c):
            return code[:17] + c
    for i in range(17):
        for alt in _ID_DIGIT_ALT.get(code[i], []):
            cand = code[:i] + alt + code[i + 1:]
            if _id_ok(cand):
                return cand
    return ""


def _find_id_number(text: str) -> str:
    """提取 18 位公民身份号码：标签取值 -> 全文候选 -> 字母纠错 -> 校验位纠错。"""
    pool: list[str] = []
    m = re.search(
        r"(?:公民身份号码|公民身份|身份号码|份证号码|证件号码|号\s*码)[:：]?\s*"
        r"([0-9A-Za-z]{10,18}(?:[ \t]*[0-9A-Za-z]{1,8})?)",
        text,
    )
    if m:
        pool.append(re.sub(r"\s", "", m.group(1)))
    # 宽松全集：号码上下文里的字母必为形近误识。
    pool.extend(
        re.findall(rf"(?<![0-9A-Za-z!|]){_ID_LOOSE}{{15,19}}(?![0-9A-Za-z!|])", text)
    )

    seen: set[str] = set()
    uniq: list[str] = []
    for raw in pool:
        # 宽松匹配可能多吞/少吞 1 个字符，滑动取全部 18 位窗口。
        for start in range(0, max(1, len(raw) - 17)):
            seg = raw[start:start + 18]
            if len(seg) != 18:
                continue
            fixed = _fix_num(seg).upper()
            if re.fullmatch(r"\d{17}[0-9X]", fixed) and fixed not in seen:
                seen.add(fixed)
                uniq.append(fixed)
    for c in uniq:
        if _id_ok(c):
            return c
    for c in uniq:
        fixed = _correct_id_number(c)
        if fixed:
            return fixed
    # 兜底：校验不过仍返回最像号码的候选（保留原有 best-effort 行为）。
    return uniq[0] if uniq else ""


# ---------------------------------------------------------------------------
# 身份证人像面
# ---------------------------------------------------------------------------
# 「住址」常换 2~3 行，OCR 拆成多行；按地址用字向下拼接。
_ADDR_KEYWORDS = tuple("省市区县乡镇街道路弄号栋幢室单元楼组村社区院巷道街村委")
_ADDR_STOP = ("公民身份", "身份号码", "份证号码", "签发", "有效期", "号码")
# 非地址行常见词：拼地址时跳过。
_ADDR_SKIP = ("姓名", "性别", "民族", "出生", "CHINA", "中国",
              "居民身份证", "照片", "中华人民共和国")

# 正面底纹水印词：含这些词的行通常不是有效字段。
_ID_WM_WORDS = ("居民身份证", "身份证", "份证", "CHINA", "中国", "居民")


def _is_watermark_line(ln: str) -> bool:
    """水印行判定：含底纹词的行剔除；但含门牌号的地址行（如「居民区3号楼」）保留。"""
    s = (ln or "").strip()
    if not s or not any(w in s for w in _ID_WM_WORDS):
        return False
    # 「居委会/居民区」等真实地址行含「居民」但带数字门牌 + 地址用字，不能误删。
    if re.search(r"\d", s) and sum(s.count(k) for k in _ADDR_KEYWORDS) >= 2:
        return False
    return True


# 地址末尾可能孤立成单字行（「房」「室」），仅在上一段以数字结尾时拼接。
_ADDR_TAIL_CHARS = "房室号栋幢层铺楼院组户店园"
# 向前回溯补齐时的拦截词：遇到这些标签说明已越过地址区。
_ADDR_HEAD_STOP = ("姓名", "性别", "民族", "出生", "照片", "公民", "号码",
                  "签发", "有效", "机关")


def _id_front_address(lines: list[str]) -> str:
    label_idx = -1
    inline = ""
    for i, raw in enumerate(lines):
        m = re.search(r"(?:住\s*址|地\s*址|住\s*所)[:：]?\s*(.*)", raw or "")
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
        if any(k in s for k in _ADDR_KEYWORDS) or len(re.findall(r"[一-龥]", s)) >= 3:
            parts.append(s)
            continue
        # 纯拉丁/短残片多为水印碎片（「CHIN」「国CHINA」），跳过而不终止拼接；
        # 单字地址尾（「房」「室」）上一段以数字结尾时才接。
        zh = re.findall(r"[一-龥]", s)
        if not zh or (len(zh) <= 2 and all(c not in _ADDR_TAIL_CHARS for c in zh)):
            continue
        if (len(s) <= 2 and all(c in _ADDR_TAIL_CHARS for c in s)
                and parts and parts[-1][-1:].isdigit()):
            parts.append(s)
            continue
        break
    addr = "".join(parts).strip()
    # 竖排/换行可能让地址首行排在「住址」标签之前：结果不以省市开头时向前回溯补齐。
    if addr and not re.match(r"^[^\s]{0,3}(?:省|市|自治区|特别行政区)", addr):
        head: list[str] = []
        for j in range(label_idx - 1, max(-1, label_idx - 4), -1):
            s = (lines[j] or "").strip()
            if not s:
                continue
            if (len(s) >= 4 and re.search(r"[省市区县]", s)
                    and not re.search(r"\d{6,}", s)
                    and not any(k in s for k in _ADDR_HEAD_STOP)):
                head.insert(0, s)
                continue
            break
        if head:
            addr = "".join(head) + addr
    return addr


def _guess_id_address(lines: list[str]) -> str:
    """住址标签完全丢失时的兜底：挑含地址用字最多、不像其它字段的连续段。"""
    best = ""
    run: list[str] = []

    def flush():
        nonlocal best
        s = "".join(run)
        if len(s) > len(best) and re.search(r"[省市区县镇乡村路街道弄号栋幢室院]", s):
            best = s
        run.clear()

    for raw in lines:
        ln = re.sub(r"\s", "", raw or "")
        ok = (
            len(ln) >= 6
            and not re.search(r"\d{6,}", ln)
            and not any(k in ln for k in (
                "号码", "姓名", "性别", "民族", "出生", "签发", "有效",
                "公民", "份证", "共和国", "照片", "机关",
            ))
            and (
                sum(ln.count(k) for k in _ADDR_KEYWORDS) >= 2
                or re.search(r"[省市区县].*[路街道号室栋弄]", ln)
            )
        )
        if ok:
            run.append(ln)
        else:
            flush()
    flush()
    return best


def _guess_id_name(lines: list[str]) -> str:
    """「姓名」标签丢失/拆行时的兜底：正面版式姓名在最上方，取顶部首个纯姓名形态的行。"""
    for raw in lines[:10]:
        ln = re.sub(r"\s", "", raw or "")
        # 扫到其它字段标签说明姓名区已过，再往下只会误吃民族/住址等字段值。
        if any(k in ln for k in (
            "性别", "民族", "出生", "住址", "地址", "公民", "号码", "签发", "有效",
        )):
            break
        if not (2 <= len(ln) <= 4):
            continue
        if not re.fullmatch(r"[一-龥·]+", ln):
            continue
        if any(k in ln for k in _ADDR_KEYWORDS):
            # 「朝阳区」这类短地名行不能当姓名。
            continue
        if any(k in ln for k in (
            "姓名", "份证", "居民", "共和", "照片", "机关", "期",
            "证", "份", "族",
        )):
            continue
        return ln
    return ""


def extract_fields(doc_type: str, lines: list[str]) -> dict[str, Any]:
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
    if doc_type == "id_card_front":
        # 正面底纹常含「中国 CHINA 居民身份证」水印，CLAHE 增强后易被 OCR 读出，
        # 倾斜件尤甚，会污染「姓名」。先剔除水印行（含门牌号的地址行除外）。
        lines = [ln for ln in lines if not _is_watermark_line(ln)]
        text = _join_text(lines)
        if not text:
            return fields
        m = re.search(
            r"姓\s*名[:：]?\s*([一-龥·](?:[ \t]*[一-龥·]){1,7})",
            text,
        )
        if m:
            cand = re.sub(r"\s+", "", m.group(1))
            cand = re.sub(r"(?:性别|民族|出生|住址|公民|号码).*$", "", cand)
            # 「性」单字尾巴是「性别」标签被截断的残留，真实姓名不会以「性」结尾。
            if len(cand) > 2 and cand.endswith("性"):
                cand = cand[:-1]
            # 「证/份/族」是底纹/民族字段的误识碎片，真实姓名几乎不含这些字。
            if 2 <= len(cand) <= 8 and not re.search(r"[证份族]", cand):
                fields["name"] = cand
        if not fields["name"]:
            fields["name"] = _guess_id_name(lines)
        addr = _id_front_address(lines)
        if not addr:
            m = re.search(r"(?:住址|地址|住所)[:：]?\s*([^\n]+)", text)
            if m:
                addr = m.group(1).strip()
        if not addr:
            addr = _guess_id_address(lines)
        fields["address"] = _fix_common_ocr_typos(addr)
        fields["id_number"] = _find_id_number(text)
        return fields

    if doc_type == "id_card_back":
        text = _join_text(lines)
        if not text:
            return fields
        # 「有效期限」标签可能与日期拆行或整行丢失：先按标签取值，失败则全文兜底——
        # 国徽面除有效期限外一般没有其它日期，全局取日期区间是安全的。
        fixed = _fix_num(text)
        # 标签后的取值必须真的含日期/长期，否则可能是「有效期」前缀误吃「有效期限」
        # 只剩「限」字残片，或日期排在标签上一行——此时回退全文兜底。
        m = re.search(r"(?:有效期限|有效期|期\s*限)[:：]?\s*([^\n]+)", fixed)
        seg = m.group(1) if m else ""
        dates = _find_dates(seg)
        if not dates and not _is_long_term(seg):
            seg = fixed
            dates = _find_dates(fixed)
        if _is_long_term(seg):
            fields["is_long_term"] = True
            if dates:
                fields["valid_from"] = dates[0]
        elif len(dates) >= 2:
            fields["valid_from"] = dates[0]
            fields["expired_at"] = dates[-1]
        elif len(dates) == 1:
            # 单日期：位于「至/-」之后为截止日，否则为起始日。
            dpos = re.search(r"\d{4}", seg)
            sep = re.search(r"[至到\-~]", seg)
            if sep and dpos and dpos.start() > sep.start():
                fields["expired_at"] = dates[0]
            else:
                fields["valid_from"] = dates[0]
        return fields

    return fields
