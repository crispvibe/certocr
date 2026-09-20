---
name: certocr-eval
description: certocr 身份证 OCR 服务的本地评测与测试方法（样本生成、识别率评测、单元测试、起服务冒烟）
---

# certocr 评测 / 测试

## 环境

- `onnxruntime==1.16.3` 无 cp312 wheel：venv 必须 **Python 3.11**（`uv venv .venv --python 3.11`）。
- `requirements.txt` 只含服务依赖；评测还需 `pytest pillow opencv-python-headless`。
- `numpy` 必须 <2（requirements 已锁），否则 onnxruntime 1.16.x 导入即崩。
- Windows 下中文 print/JSON 读写需 `PYTHONUTF8=1`，否则 cp1252 编码报错。

## 命令（Windows bash 会话）

```bash
uv pip install --python .venv/Scripts/python.exe -r requirements.txt pytest pillow opencv-python-headless==4.10.0.84 opencv-python==4.10.0.84
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest test_parsers.py   # 纯解析单测，秒级
PYTHONUTF8=1 .venv/Scripts/python.exe gen_idcards.py 10           # 生成 120 张合成评测图（6 种退化）
PYTHONUTF8=1 .venv/Scripts/python.exe eval_idcards.py             # 真 OCR 评测，~10min，报告在 test_images/idcards/_report.json
```

## 冒烟起服务

```bash
HEYU_UPLOAD_ROOT="<test_images 绝对路径>" PORT=8099 .venv/Scripts/python.exe main.py
curl -X POST http://127.0.0.1:8099/parse -H 'Content-Type: application/json' \
  -d '{"doc_type":"id_card_front","image_path":"<图绝对路径>"}'
```

- `doc_type` 仅接受 `id_card_front` / `id_card_back`，其余 400。
- `image_path` 必须落在 `HEYU_UPLOAD_ROOT` 白名单内；`image_url` 走 SSRF 校验，本地测试用 image_path 即可。
- `test_images/` 在 .gitignore 中，评测产物不入库。
