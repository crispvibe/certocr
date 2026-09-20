# certocr · 身份证结构化识别服务

> 基于 RapidOCR 的轻量级 HTTP 服务，输入一张身份证照片（人像面/国徽面），返回结构化字段（JSON）。
> 本地离线、CPU 可跑、易于自部署。

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688.svg)](https://fastapi.tiangolo.com/)
[![OCR](https://img.shields.io/badge/OCR-RapidOCR%20(ONNX)-orange.svg)](https://github.com/RapidAI/RapidOCR)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

---

## 这是什么

实名认证、开户审核等业务需要把身份证照片上的信息录入系统，人工抄录又慢又容易错。

这个服务做的事很简单：**给它一张身份证照片，它把上面的关键字段识别出来，整理成结构化 JSON 返回**，供后台直接回填。

- 纯本地推理，**不依赖任何云 OCR、不外发图片**，数据不出内网。
- 模型用的是 RapidOCR（ONNXRuntime），CPU 即可跑，无需 GPU。
- 针对身份证版面做了**字段解析与纠错规则**：身份证号会走 ISO 7064 校验位反推纠错，姓名/住址/有效期限在标签丢失时也有兜底提取，不是简单地把文字堆给你。

## 输出字段

| `doc_type`      | 证照类型        | 主要输出字段                                              |
| --------------- | --------------- | --------------------------------------------------------- |
| `id_card_front` | 身份证（人像面）| `name` 姓名、`address` 住址、`id_number` 公民身份号码     |
| `id_card_back`  | 身份证（国徽面）| `valid_from` / `expired_at` 有效期限、`is_long_term` 是否长期 |

统一返回结构（未识别到的字段为空字符串 / `false`，不会缺键）：

```json
{
  "doc_type": "id_card_front",
  "fields": {
    "name": "张三",
    "address": "北京市朝阳区某街道1号",
    "legal_person": "",
    "credit_code": "",
    "id_number": "11010119900101001X",
    "valid_from": "",
    "valid_to": "",
    "expired_at": "",
    "is_long_term": false
  },
  "raw_text": "……识别到的完整文本……",
  "engine": "RapidOCR"
}
```

## 识别为什么更准

手机翻拍的身份证常有倾斜、反光、淡色水印遮挡，普通 OCR 直接识别召回率不稳。本服务做了两层容错：

**送引擎前 —— 多通道预处理 + 取并集：**

1. **自动纠偏**：用 Hough 直线检测估算整页倾角，小角度自动校正（手机翻拍常见的几度倾斜）。
2. **CLAHE 对比度增强**：提升淡色字体、水印遮挡区域的检测召回。
3. **多帧并集去重**：原图 + 增强图（+ 纠偏图）分别识别，按行取并集。
4. **低召回救回**：常规通道产出过少时，自动追加「放大 + Otsu 二值化」帧再扫一次，专治过暗/模糊/低清的极端翻拍件。

**出引擎后 —— 规则化字段解析 + 校验纠错：**

1. **身份证号校验纠错**：先按标签与 18 位候选定位，形近字母（O/I/S/B 等）自动翻译回数字；校验位不过时先修校验码、再对出生日期段做单点纠错——「校验位通过 + 出生日期合法」双约束，纠得准且几乎不误纠。
2. **标签丢失兜底**：「姓名」「住址」「有效期限」标签被 OCR 吃掉时，按身份证版式（姓名在顶部、地址形态、国徽面只有一组日期）全局兜底提取。
3. **版面噪声免疫**：正面底纹「中国 CHINA 居民身份证」水印行自动剔除（带门牌号的「居民区」地址行会保留）；地址跨行自动拼接，水印碎片与孤立单字尾（「房」「室」）都能正确处理；日期容忍全角数字、分隔符空格等常见误识。

## 快速开始

```bash
cd certocr
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

服务默认监听 `8091` 端口。健康检查：

```bash
curl http://127.0.0.1:8091/health
# {"status":"ok","engine":"RapidOCR"}
```

## API

### `POST /parse`

请求体（`image_url` 与 `image_path` 二选一）：

```json
{
  "doc_type": "id_card_front",
  "image_url": "https://example.com/uploads/xxx.jpg"
}
```

| 字段         | 说明                                                              |
| ------------ | ----------------------------------------------------------------- |
| `doc_type`   | 必填，`id_card_front` 或 `id_card_back`                           |
| `image_url`  | 公网可访问的图片地址（http/https），或白名单内的本地相对/绝对路径 |
| `image_path` | 白名单目录内的本地文件路径（与 `image_url` 二选一）               |

调用示例：

```bash
curl -X POST http://127.0.0.1:8091/parse \
  -H "Content-Type: application/json" \
  -d '{"doc_type":"id_card_front","image_url":"https://example.com/a.jpg"}'
```

## Docker 部署

```bash
docker build -t certocr .
docker run -d -p 127.0.0.1:8091:8091 certocr
```

或使用 `docker-compose.yml`：

```bash
docker compose up -d
```

> 建议只绑定到 `127.0.0.1`，由上层网关/后端转发，**不要把 OCR 端口直接暴露到公网**。

## 环境变量

| 变量                  | 默认值                              | 说明                                                       |
| --------------------- | ----------------------------------- | ---------------------------------------------------------- |
| `PORT`                | `8091`                              | 服务监听端口                                               |
| `HEYU_OCR_TOKEN`      | 空（不启用）                        | 设置后要求请求头携带 `X-Internal-Token`，作为内网纵深防御  |
| `HEYU_UPLOAD_ROOT`    | `/www/server/heyu-cy/uploads/file`  | 本地图片读取的根目录白名单                                 |
| `HEYU_ALLOWED_ROOTS`  | 空                                  | 追加的白名单根目录，多个用系统路径分隔符分隔               |

## 安全设计

这个服务面向内网调用，做了几层防护，避免被当成「跳板」：

- **SSRF 防护**：下载远程图片前先解析目标 IP，拒绝私网 / 环回 / 链路本地 / 保留地址，并禁止重定向，防止被诱导访问云元数据或内网服务。
- **路径穿越防护**：本地图片只能落在白名单根目录内，软链接和 `..` 穿越会被拦截。
- **下载体积上限**：单张图片限制 15MB，防止被诱导拉取超大响应耗尽资源。
- **可选内网鉴权**：配置 `HEYU_OCR_TOKEN` 后强制校验请求头令牌。

## 测试与评测

```bash
pip install pytest
pytest test_parsers.py -v
```

`test_parsers.py` 覆盖身份证字段解析与容错规则。`gen_idcards.py` / `eval_idcards.py` 为离线样本生成与识别率评测脚本（仅用于开发调优，样本图自行生成不入库）：

```bash
python gen_idcards.py 10        # 生成 10 人 × 正反面 × 6 种退化共 120 张测试图
python eval_idcards.py          # 跑真实 OCR + 解析，输出逐字段识别率
```

## 目录结构

```
certocr/
├── main.py              # FastAPI 入口：图片获取、预处理、OCR、安全校验
├── parsers.py           # 身份证字段解析与容错规则
├── test_parsers.py      # 解析单元测试
├── gen_idcards.py       # 身份证测试图生成（开发用）
├── eval_idcards.py      # 识别率评测（开发用）
├── requirements.txt     # 依赖
├── Dockerfile           # 容器构建
├── docker-compose.yml   # 一键部署
└── README.md
```

## 技术栈

- **FastAPI + Uvicorn** — 异步 HTTP 服务
- **RapidOCR (ONNXRuntime)** — 离线 OCR 引擎，CPU 可跑
- **OpenCV** — 图像预处理（灰度、CLAHE、纠偏、二值化）

## 开源协议

本项目以 [MIT](./LICENSE) 协议开源，可自由使用、修改与商用，保留版权声明即可。

## 作者

**Anna** · 个人主页：[www.anna.tf](https://www.anna.tf/)

欢迎提 Issue / PR 交流改进。
