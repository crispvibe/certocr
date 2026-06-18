# GitHub 发布与配置指南

把本服务作为一个独立仓库开源到 GitHub 的完整步骤与配置建议。照着做即可。

---

## 一、仓库名称

已确定：**`certocr`**（仓库地址：`https://github.com/crispvibe/certocr`）。

## 二、仓库 About（一句话简介）

填到仓库页右上角 **About → Description**：

```
中文证照结构化 OCR 服务：营业执照 / 身份证 / 食品经营许可证一图识别，纯本地离线、返回结构化 JSON。
```

英文版（如需）：

```
Self-hosted OCR microservice that turns Chinese certificates (business license, ID card, food permit) into structured JSON. Offline, CPU-only, powered by RapidOCR.
```

## 三、Topics（标签）

在 About 里点 ⚙️ 添加以下 topics，便于被检索：

```
ocr  rapidocr  fastapi  python  chinese-ocr  business-license  id-card  document-parsing  onnxruntime  self-hosted
```

## 四、上传到 GitHub

> 当前目录 `certocr`（即 `ocr-service/`）位于一个更大的项目仓库内。开源时把它作为**独立仓库**单独初始化、单独推送即可，不影响原项目。

GitHub 上已建好空仓库 `crispvibe/certocr`。在本目录（`ocr-service/`）下执行：

```bash
git init
git add .
git commit -m "chore: 首次开源发布 certocr"
git branch -M main
git remote add origin https://github.com/crispvibe/certocr.git
git push -u origin main
```

> 若用 SSH，远程地址改为 `git@github.com:crispvibe/certocr.git`。

## 五、发布前检查清单

- [x] `README.md` 已就绪（含功能、API、部署、安全说明）
- [x] `LICENSE` 已添加（MIT，署名 Anna）
- [x] `.gitignore` 已排除 `.venv/`、`__pycache__/`、`_exp_*.py`、`test_images/`
- [ ] 确认代码内**无任何密钥、内网地址、真实证件样本**
- [ ] 大体积测试样本（`test_images/`）不要提交，已在 `.gitignore` 中忽略
- [ ] 推送后在仓库页填写 **About** 与 **Topics**

## 六、发布后建议

- 打第一个 Tag：`git tag v1.0.0 && git push --tags`，并在 GitHub 上创建 Release。
- 在仓库 Settings → 开启 Issues，方便收集反馈。
- 如需展示效果，可在 README 顶部加一张识别示例图（注意脱敏）。

---

作者：**Anna** · 协议：MIT
