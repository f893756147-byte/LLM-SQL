# LLM-SQL
一个基于 `Streamlit` 的轻量应用：通过自然语言对 MySQL 执行增删改查（CRUD）。  
应用内置一个可被大模型调用的数据库工具，支持 OpenAI 兼容接口（如 DeepSeek 等）。

## 功能特性

- 自然语言驱动 SQL 操作（由 LLM 自动选择是否调用数据库工具）
- 内置 MySQL CRUD 工具：建表、插入、查询、更新、删除
- Web 配置页：可视化配置数据库与 LLM 参数
- 支持本地保存配置（可选择是否保存敏感信息）
- 支持自定义 `system prompt`

## 技术栈

- Python 3.10+
- Streamlit
- OpenAI Python SDK（兼容 OpenAI 格式接口）
- PyMySQL

## 项目结构

```text
.
├── streamlit_app.py    # Web 应用入口（配置 + 对话）
├── llm_module.py       # LLM 模块与工具调用编排
├── llm_db_tool.py      # MySQL CRUD 工具实现
└── requirements.txt    # Python 依赖
```

## 快速开始

### 1) 克隆项目

```bash
git clone <your-repo-url>
cd <your-repo-folder>
```

### 2) 创建并激活虚拟环境（推荐）

```bash
python -m venv .venv
```

Windows（PowerShell）：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
source .venv/bin/activate
```

### 3) 安装依赖

```bash
pip install -r requirements.txt
```

### 4) 启动应用

```bash
streamlit run streamlit_app.py
```

启动后在浏览器打开 Streamlit 提示的本地地址（通常是 `http://localhost:8501`）。

## 配置说明

首次进入页面需要填写以下配置：

- MySQL 配置：`host`、`port`、`user`、`password`、`database`
- LLM 配置：`api_key`、`model`、`base_url`（可选）
- `system prompt`：定义助手行为

### 推荐的环境变量（可选）

虽然当前 Web 版本主要通过页面输入配置，但模块本身也支持从环境变量读取：

- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `DB_CHARSET`
- `LLM_API_KEY`（或兼容变量）
- `LLM_MODEL`
- `LLM_MAX_TOOL_ROUNDS`

## 使用示例

在聊天框输入自然语言，例如：

- `查询 users 表最近 10 条数据`
- `创建一个 users 表，包含 id、name、age`
- `给 name=Alice 的用户把 age 改成 23`
- `删除 name=Bob 的记录`

## 安全提示

- 请务必使用最小权限的数据库账号，避免使用高权限生产账号
- 不建议在本地配置文件中保存明文密码和 API Key


## 注意事项

- 当前数据库工具的表名/字段名由输入拼接，生产环境建议增加白名单与更严格的参数校验
- 若使用第三方 OpenAI 兼容平台，请确保 `base_url` 与 `model` 正确
- 初次连接会进行一条轻量查询用于连通性测试

## License

可根据需要添加，例如 `MIT`。
