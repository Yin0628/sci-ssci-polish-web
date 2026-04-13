# SCI/SSCI 在线润色网站（OpenAI + DeepSeek）

这个目录是一个可公网部署的统一润色站点，支持：
- OpenAI 引擎润色
- DeepSeek 引擎润色
- 上传 `.docx` / `.pdf`
- 下载段落级 HTML 润色报告
- 手机与电脑浏览器访问

## 目录说明

- `app.py`: 网站主程序（Streamlit）
- `openai_polisher.py`: OpenAI 润色引擎
- `deepseek_polisher.py`: DeepSeek 润色引擎
- `document_parser.py`: 文档解析
- `report_writer.py`: HTML 报告生成
- `Dockerfile` / `render.yaml`: 公网部署配置

## 本地运行

```bash
cd SCI_SSCI_在线润色网站
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## 公网部署（Render）

1. 把该目录推到 GitHub 仓库
2. 在 Render 新建 Web Service，选择该仓库
3. Render 会自动识别 `render.yaml` 与 `Dockerfile`
4. 在 Render 环境变量里配置（至少一个）：
   - `OPENAI_API_KEY`
   - `DEEPSEEK_API_KEY`
5. 部署完成后，你会得到一个公开 HTTPS 链接，任何人可访问

## 可选：部署到 Streamlit Community Cloud

1. 推到 GitHub
2. 在 Streamlit Cloud 连接仓库并选择 `SCI_SSCI_在线润色网站/app.py`
3. 在 Secrets 配置 API Key
4. 部署后即可公开访问

## 注意

- 公网部署后，任何访问者都可能消耗你的 API 额度。
- 建议后续增加登录、限流、支付与订单验证模块。


## 安全加固（已内置）

应用已支持以下环境变量：
- `SITE_ACCESS_CODE`：访问口令（设置后用户需输入口令）
- `MAX_UPLOAD_MB`：单文件大小上限，默认 `20`
- `MAX_SOURCE_CHARS`：单次文本字符上限，默认 `120000`
- `MAX_BLOCK_COUNT`：解析块数量上限，默认 `400`
- `MAX_REPORT_ROWS`：报告条目上限，默认 `400`
- `MIN_SECONDS_BETWEEN_JOBS`：同会话最小提交间隔秒数，默认 `30`
- `DAILY_REQUEST_LIMIT`：单会话每日调用上限，默认 `80`
- `ALLOW_USER_SUPPLIED_KEYS`：是否允许前端覆盖API key，默认 `false`


## 支付与订单校验（已内置）

当前版本采用“收款码 + 提交凭证 + 审核放行”模式（已兼容 OpenAI / DeepSeek 双引擎）：
1. 用户先上传文件并检测字数，系统自动生成订单与金额。
2. 用户扫码支付（微信/支付宝）并提交支付凭证。
3. 管理员输入 `ADMIN_REVIEW_CODE` 审核通过后，订单状态变为 `paid`。
4. 只有 `paid` 订单才允许执行润色。

请在 Render 环境变量中配置：
- `ADMIN_REVIEW_CODE`
- `WECHAT_PAY_QR_URL`
- `ALIPAY_PAY_QR_URL`
- （可选）模型价格参数（按 1000 字与最低价）：
  - `PRICE_GPT_3_5_TURBO_PER_1K` / `PRICE_GPT_3_5_TURBO_MIN`
  - `PRICE_DEEPSEEK_CHAT_PER_1K` / `PRICE_DEEPSEEK_CHAT_MIN`
  - `PRICE_GPT_4O_MINI_PER_1K` / `PRICE_GPT_4O_MINI_MIN`
  - `PRICE_DEEPSEEK_REASONER_PER_1K` / `PRICE_DEEPSEEK_REASONER_MIN`
  - `PRICE_GPT_4O_PER_1K` / `PRICE_GPT_4O_MIN`

说明：免费实例磁盘是临时的，订单库默认在 `/tmp`，重启后可能清空。
如需持久化订单，请升级实例并挂载持久化存储（或接入外部数据库）。

## 未来自动校验（商户参数预留）

当前已预留以下参数位，后续你提供商户资料后可切到“自动验单”：
- 微信：`WECHAT_MCH_ID`、`WECHAT_APP_ID`、`WECHAT_API_V3_KEY`、`WECHAT_MCH_SERIAL_NO`、`WECHAT_PRIVATE_KEY_PATH`
- 支付宝：`ALIPAY_APP_ID`、`ALIPAY_APP_PRIVATE_KEY_PATH`、`ALIPAY_PUBLIC_KEY`
