# certocr · 中文证照结构化识别服务

> 基于 RapidOCR 的轻量级 HTTP 服务，输入一张证照图片，返回结构化字段（JSON）。
> 已支持营业执照、身份证正反面、食品经营许可证，开箱即用、本地离线、易于自部署。

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688.svg)](https://fastapi.tiangolo.com/)
[![OCR](https://img.shields.io/badge/OCR-RapidOCR%20(ONNX)-orange.svg)](https://github.com/RapidAI/RapidOCR)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

---

## 这是什么

很多业务（商家入驻、实名认证、资质审核）都需要把证件照片上的信息录入系统。人工抄录又慢又容易错。

这个服务做的事很简单：**给它一张证照图，它把上面的关键字段识别出来，整理成结构化 JSON 返回**，供后台直接回填。

- 纯本地推理，**不依赖任何云 OCR、不外发图片**，数据不出内网。
- 模型用的是 RapidOCR（ONNXRuntime），CPU 即可跑，无需 GPU。
- 针对中文证照版面做了大量**字段解析规则**，不是简单地把文字堆给你，而是直接给到「名称 / 地址 / 法人 / 信用代码 / 有效期」这类可用字段。

## 支持的证照与输出字段

| `doc_type`         | 证照类型       | 主要输出字段                                                       |
| ------------------ | -------------- | ------------------------------------------------------------------ |
| `business_license` | 营业执照       | `name` 名称、`address` 住所、`legal_person` 法人、`credit_code` 统一社会信用代码、有效期 |
| `id_card_front`    | 身份证（人像面）| `name` 姓名、`address` 住址、`id_number` 公民身份号码              |
| `id_card_back`     | 身份证（国徽面）| `valid_from` / `valid_to` 有效期限、`is_long_term` 是否长期        |
| `food_license`     | 食品经营许可证 | `name` 名称、`address` 地址、`legal_person` 负责人、有效期         |

统一返回结构（未识别到的字段为空字符串 / `false`，不会缺键）：

```json
{
  "doc_type": "business_license",
  "fields": {
    "name": "某某餐饮服务有限公司",
    "address": "某省某市某区某路1号",
    "legal_person": "张三",
    "credit_code": "91XXXXXXXXXXXXXXXX",
    "id_number": "",
    "valid_from": "2020-01-01",
    "valid_to": "",
    "expired_at": "",
    "is_long_term": true
  },
  "raw_text": "……识别到的完整文本……",
  "engine": "RapidOCR"
}
```

## 识别为什么更准

手机翻拍的证照常有倾斜、反光、淡色水印遮挡，普通 OCR 直接识别召回率不稳。本服务在送入引擎前做了**多通道预处理 + 取并集**：

1. **自动纠偏**：用 Hough 直线检测估算整页倾角，小角度自动校正（手机翻拍常见的几度倾斜）。
2. **CLAHE 对比度增强**：提升淡色字体、水印遮挡区域（如营业执照「名称」行）的检测召回。
3. **多帧并集去重**：原图 + 增强图（+ 纠偏图）分别识别，按行取并集，兼顾常规字段与疑难字段。
4. **规则化字段解析**：针对中文证照版面（两栏布局、标签换行、长期/永久有效等）做了大量兜底解析，地址续行拼接也会自动剔除页脚提示语。

## 快速开始

```bash
cd certocr
python3 -m venv .venv
source .venv/bin/activate
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
  "doc_type": "business_license",
  "image_url": "https://example.com/uploads/xxx.jpg"
}
```

| 字段         | 说明                                                              |
| ------------ | ----------------------------------------------------------------- |
| `doc_type`   | 必填，取值见上方表格                                              |
| `image_url`  | 公网可访问的图片地址（http/https），或白名单内的本地相对/绝对路径 |
| `image_path` | 白名单目录内的本地文件路径（与 `image_url` 二选一）               |

调用示例：

```bash
curl -X POST http://127.0.0.1:8091/parse \
  -H "Content-Type: application/json" \
  -d '{"doc_type":"business_license","image_url":"https://example.com/a.jpg"}'
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

## 测试

```bash
pip install pytest
pytest test_parsers.py -v
```

`test_parsers.py` 覆盖各类证照的字段解析；`eval_*.py`、`gen_*.py` 为离线评测与样本生成脚本，仅用于开发调优。

## 目录结构

```
certocr/
├── main.py              # FastAPI 入口：图片获取、预处理、OCR、安全校验
├── parsers.py           # 各类证照的字段解析规则
├── test_parsers.py      # 解析单元测试
├── requirements.txt     # 依赖
├── Dockerfile           # 容器构建
├── docker-compose.yml   # 一键部署
└── README.md
```

## 技术栈

- **FastAPI + Uvicorn** — 异步 HTTP 服务
- **RapidOCR (ONNXRuntime)** — 离线 OCR 引擎，CPU 可跑
- **OpenCV** — 图像预处理（灰度、CLAHE、纠偏）

## 开源协议

本项目以 [MIT](./LICENSE) 协议开源，可自由使用、修改与商用，保留版权声明即可。

## 作者

**Anna** · 个人主页：[www.anna.tf](https://www.anna.tf/)

欢迎提 Issue / PR 交流改进。
