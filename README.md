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
