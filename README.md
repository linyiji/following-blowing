# Following blowing · BYOK Edition

Following blowing 是一个可本地运行的 AI IP × Brand 联名设计工作流。它通过 IP Identity Grammar 保护角色身份，允许姿势、视角、服装和互动发生合法变化。

> Following blowing does not ship with API credentials.

BYOK（Bring Your Own Key）版本不附带、预置或代理任何 API Key。用户通过应用内的 **⚙ API 设置** 连接自己的 OpenAI-compatible Provider；没有凭证时仍可以明确选择 Demo Mode。

## 快速启动

请先安装 **Python 3.12 或 3.13**，并在解压后的项目根目录中执行命令。不要直接在 ZIP 预览窗口中运行。

### macOS

打开“终端”，进入解压后的目录：

```bash
cd /path/to/following-blowing-byok
python3 --version
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m streamlit run streamlit_app.py
```

也可以双击 `start_macos.command`。如果 macOS 首次拦截脚本，可在终端中执行：

```bash
chmod +x start_macos.command
./start_macos.command
```

### Windows 10 / 11

建议从 [python.org](https://www.python.org/downloads/) 安装 Python 3.12 或 3.13，安装时勾选 **Add Python to PATH**。在解压后的项目目录空白处点击地址栏，输入 `cmd` 并回车，然后执行：

```bat
py -3.12 --version
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

也可以直接双击 `start_windows.bat`。这两种方式都直接调用虚拟环境中的 Python，不需要执行 `activate`，因此不受 PowerShell 执行策略影响。

启动成功后，浏览器打开 [http://localhost:8501](http://localhost:8501)。终端窗口需保持打开；要停止应用，在终端按 `Ctrl+C`。

### 常见部署问题

- `python3` / `py` 找不到：重新安装 Python，并确保加入 PATH。
- `No module named streamlit`：请用上面的 `.venv/.../python -m pip install -r requirements.txt`，不要使用系统 `pip`。
- `streamlit` 命令找不到：使用 `python -m streamlit`形式，如上述命令。
- 8501 端口被占用：在启动命令后加 `--server.port 8502`，然后打开 `http://localhost:8502`。
- 安装依赖失败：先确认 Python 是 3.12/3.13，再删除解压目录中自己生成的 `.venv` 并重试。
- API 未配置不影响页面启动；启动后请在右上角 **⚙ API 设置** 中填入自己的 Key。本 GitHub 仓库不包含 API Key。

## 首次使用：6 步

1. 运行应用并打开 Following blowing。
2. 点击右上角 **⚙ API 设置**。
3. 选择 Provider，输入自己的 API Key、Base URL 和 FAST / MAIN / IMAGE 模型。
4. 点击 **测试连接**。
5. 测试通过后点击 **保存设置**，并确认 AI Services / Health 状态已就绪。
6. 回到主页，上传或选择 IP / 品牌图片，然后启动 Workflow。

普通用户无需也不应手工编辑 `.streamlit/secrets.toml`。

## API 设置

### Provider

API Settings 提供两类入口：

- **Custom OpenAI Compatible**：由用户填写 Provider 的 Base URL 和模型 ID。
- **TeamoRouter preset**：仅填入公开的 Base URL `https://api.teamorouter.com/v1` 和建议模型名。

TeamoRouter 不是唯一 Provider。Preset 不含 API Key，Key 输入框始终由用户自己填写。

### 模型角色

| 逻辑路由 | 用途 | 建议值，可修改 |
| --- | --- | --- |
| FAST | AI Supplement、Design Package 文案和低风险文本整理 | `gpt-5.6-luna` |
| MAIN | 结构化推理、单图视觉分析和双图 Guardian | `gpt-5.6-terra` |
| IMAGE | Fusion Generation 与 Guardian 修订图 | `gpt-image-2` |

这三个逻辑角色是固定的，具体模型 ID 由用户在运行时配置。MAIN 模型必须满足项目需要的视觉和结构化输出能力；IMAGE 模型需要支持图片生成和单参考图编辑。

### 测试连接

标准连接测试会：

- 在 Provider 支持时读取模型列表。
- 执行极小的 FAST 和 MAIN 文本请求。
- 检查 IMAGE 模型的配置或目录可用性。

普通的 **测试连接** 不会自动生成收费图片。只有用户主动启动“高级图像测试”或真实 Workflow 时，才可能产生图像 API 费用。

## 凭证安全

- API Key 优先保存在操作系统的安全凭据存储中：macOS Keychain、Windows Credential Manager 或 Linux keyring backend。
- Keyring 不可用时，Key 只保留在当前 Python 会话内存中；应用退出后需重新输入。
- Provider、Base URL、模型和 timeout 等非敏感设置可持久化，API Key 不进入非敏感配置文件。
- 重新打开设置时，前端只能看到 `credential_configured=true/false`，不会从 Python 取回真实 Key。
- Key 不进入 HTML / JS 源码、localStorage、sessionStorage、日志、Checkpoint、Run 记录、Prompt trace、Workflow trace、ZIP 或 manifest。
- **删除 API 凭据** 会删除安全存储中的 Key，之后真实 Workflow 将不可用，直到重新配置。

更完整的责任边界见 [API Settings architecture](docs/architecture/api-settings.md)。

## 没有凭证时

应用必须正常打开，不会因为缺少 Key 而崩溃。主页会明确显示 **API 未配置**，用户可以：

- 点击 **配置 API** 进入设置。
- 点击 **使用 Demo** 运行不需凭证的演示流程。

Demo 会持续显示 **DEMO MODE**，不会伪装成真实 API 运行。Demo 使用内置素材和模拟 Provider，但与真实模式共用同一套 12-Agent DAG、Schema、Checkpoint、Guardian、Ranking 和 ZIP 逻辑。

Search 在本版仍为 `demo/mock`，不在首版 BYOK API Settings 中配置。没有可验证的搜索来源时，系统会明确记录 evidence gap，不会伪造联名案例。

## 12-Agent Workflow

```text
IP Preparation → IP Intelligence
Brand Intelligence → Brand Collaboration → Brand Feature
IP Intelligence + Brand Feature + User Intent
  → Creative Brief → Fusion Decision → IP Adaptation
  → Fusion Generation → Pose-Aware Guardian
  → Ranking → Design Package
```

Guardian 未 PASS 时会在可用重试次数内把分组修正指令返回 Fusion Generation。Guardian 的身份分、Compliance Gates 和最终 Verdict，以及 Ranking 的数字总分，都由 Python 确定性计算。

## 上传、恢复与导出

- 支持 PNG、JPEG 和 WebP；后端会检查文件签名、MIME、解码完整性、尺寸和哈希。
- 每次启动 Workflow 都生成独立 `run_id`。带有 `?run=<run_id>` 的本地 URL 可恢复已保存的 Checkpoint。
- 只有 Workflow 完成且 Guardian PASS 才能导出 ZIP。
- 导出包含结果图、IP Identity Grammar、Brand Feature Pool、Creative Brief、Fusion Strategy、IP Adaptation、Guardian Report、Ranking、Workflow / Prompt trace 和 Design Guide。
- API Key 永远不进入运行或导出产物。

## 当前边界

- GPT Image 2 单参考图编辑是目标支持路由；多参考图编辑仍为 `UNVERIFIED`。
- Search 仍为 Demo / Mock。
- 真实 API 会产生 Provider 费用，费用、限额和数据保留政策由用户选择的 Provider 决定。
- 应用本身不提供账号、租户隔离、长期云存储、商业计费或矢量设计文件生成。

## 开发者验证

```bash
source .venv/bin/activate
python -m pytest -q
```

付费真实 API smoke 均是显式 opt-in，不会被普通 `pytest` 自动执行。架构详情见：

- [API Settings](docs/architecture/api-settings.md)
- [Model Routing](docs/architecture/model-routing.md)
- [Agent Workflow](docs/architecture/agent-workflow.md)
- [IP Identity Grammar](docs/architecture/ip-identity-grammar.md)
- [Pose-Aware Guardian](docs/architecture/guardian.md)
- [Output Contracts](docs/architecture/output-contracts.md)

`.streamlit/secrets.toml.example` 只为开发者或部署管理员的预配置兼容入口。BYOK 普通用户应使用应用内 API Settings。
