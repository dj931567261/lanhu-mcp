# 🤖 AI 助手安装指南

> **专为 AI 助手设计的安装指导文档**
> AI 可以根据这个文档一步步引导用户完成安装和配置

---

## 📝 安装检查清单

在开始之前，AI 需要确认用户的系统环境：

```
[ ] 操作系统：Windows / Mac / Linux
[ ] 是否安装了 Python 3.10+？(python3 --version)
[ ] 是否安装了 Git？(git --version)
[ ] 是否有蓝湖账号？
[ ] 使用的 AI 客户端是什么？(Claude Code / Cursor / Codex / Cline 等)
```

---

## 🚀 安装流程

### 步骤 1：下载项目

```bash
git clone https://github.com/你的仓库地址/lanhu-mcp.git
cd lanhu-mcp
```

### 步骤 2：创建虚拟环境并安装依赖

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 步骤 3：配置蓝湖 Cookie

获取 Cookie 后，写入项目根目录的 `cookie` 文件：

```bash
echo "你的蓝湖Cookie" > cookie
```

> 📖 Cookie 获取方式参考 [GET-COOKIE-TUTORIAL.md](GET-COOKIE-TUTORIAL.md)

### 步骤 4：配置 AI 客户端

本项目使用 **stdio** 方式连接（非 HTTP），需要在 AI 客户端中配置启动脚本。

---

## 🔧 各客户端配置方式

### Claude Code

编辑 `~/.claude.json`，在 `mcpServers` 中添加：

**macOS / Linux：**
```json
{
  "mcpServers": {
    "Lanhu-mcp": {
      "command": "bash",
      "args": ["/绝对路径/lanhu-mcp/run_lanhu_mcp_stdio.sh"],
      "env": {
        "LANHU_MCP_USER_NAME": "你的名字",
        "LANHU_MCP_USER_ROLE": "Developer"
      }
    }
  }
}
```

**Windows（使用 Git Bash）：**
```json
{
  "mcpServers": {
    "Lanhu-mcp": {
      "command": "D:\\Git\\bin\\bash.exe",
      "args": ["C:/绝对路径/lanhu-mcp/run_lanhu_mcp_stdio.sh"],
      "env": {
        "LANHU_MCP_USER_NAME": "你的名字",
        "LANHU_MCP_USER_ROLE": "Developer"
      }
    }
  }
}
```
> `command` 填 Git 安装目录下 `bin\bash.exe` 的实际路径，`args` 中可使用正斜杠。

### Cursor

在 Cursor 设置中找到 MCP 配置，添加：

**macOS / Linux：**
```json
{
  "mcpServers": {
    "Lanhu-mcp": {
      "command": "bash",
      "args": ["/绝对路径/lanhu-mcp/run_lanhu_mcp_stdio.sh"],
      "env": {
        "LANHU_MCP_USER_NAME": "你的名字",
        "LANHU_MCP_USER_ROLE": "Developer"
      }
    }
  }
}
```

**Windows（使用 Git Bash）：**
```json
{
  "mcpServers": {
    "Lanhu-mcp": {
      "command": "D:\\Git\\bin\\bash.exe",
      "args": ["C:/绝对路径/lanhu-mcp/run_lanhu_mcp_stdio.sh"],
      "env": {
        "LANHU_MCP_USER_NAME": "你的名字",
        "LANHU_MCP_USER_ROLE": "Developer"
      }
    }
  }
}
```

### OpenAI Codex CLI

编辑 Codex 配置文件 `config.toml`，添加 MCP 服务器配置，添加后每次对话都可以直接使用蓝湖 MCP 工具。

**macOS / Linux**（配置文件位于 `~/.codex/config.toml`）：

```toml
[mcp_servers.Lanhu-mcp]
type = "stdio"
command = "bash"
args = ["/绝对路径/lanhu-mcp/run_lanhu_mcp_stdio.sh"]
```

**Windows（方式一：使用 Git Bash，推荐）**（配置文件位于 `%USERPROFILE%\.codex\config.toml`）：

```toml
[mcp_servers.Lanhu-mcp]
type = "stdio"
command = "D:\\Git\\bin\\bash.exe"
args = ["C:/绝对路径/lanhu-mcp/run_lanhu_mcp_stdio.sh"]
```
> `command` 填 Git 安装目录下 `bin\\bash.exe` 的实际路径，`args` 中可使用正斜杠。

**Windows（方式二：使用 cmd）**：

```toml
[mcp_servers.Lanhu-mcp]
type = "stdio"
command = "cmd"
args = ["/c", "C:\\绝对路径\\lanhu-mcp\\run_lanhu_mcp_stdio.bat"]
```

### Windsurf / Cline / 其他支持 MCP 的客户端

配置方式类似，核心参数：

**macOS / Linux：**
- `command`: `"bash"`
- `args`: `["/绝对路径/lanhu-mcp/run_lanhu_mcp_stdio.sh"]`
- `env`: 可选，设置用户名和角色

**Windows（使用 Git Bash）：**
- `command`: `"D:\\Git\\bin\\bash.exe"`（填 Git 实际安装路径）
- `args`: `["C:/绝对路径/lanhu-mcp/run_lanhu_mcp_stdio.sh"]`
- `env`: 可选，设置用户名和角色

> ⚠️ **注意**：`args` 中必须使用**绝对路径**，不能用相对路径或 `~`。

---

## 🧩 安装 Skill（可选，推荐）

项目内置 8 个平台的 Skill 文件，配合 MCP 可让 AI 直接从蓝湖设计稿生成 UI 代码。

**不需要全部安装，只安装你用得到的平台即可。** 请询问用户需要哪些平台，然后只安装对应的 Skill。

### 可选平台

| Skill 名称 | 平台 | 安装命令（Claude Code） |
|------------|------|------------------------|
| `lanhu-compose-plan` | Jetpack Compose | `cp -r skills/lanhu-compose-plan ~/.claude/skills/` |
| `lanhu-xml-plan` | Android XML | `cp -r skills/lanhu-xml-plan ~/.claude/skills/` |
| `lanhu-flutter-plan` | Flutter | `cp -r skills/lanhu-flutter-plan ~/.claude/skills/` |
| `lanhu-rn-plan` | React Native | `cp -r skills/lanhu-rn-plan ~/.claude/skills/` |
| `lanhu-swiftui-plan` | SwiftUI | `cp -r skills/lanhu-swiftui-plan ~/.claude/skills/` |
| `lanhu-vue-plan` | Vue 3 | `cp -r skills/lanhu-vue-plan ~/.claude/skills/` |
| `lanhu-html-plan` | HTML + CSS | `cp -r skills/lanhu-html-plan ~/.claude/skills/` |
| `lanhu-uniapp-plan` | uni-app | `cp -r skills/lanhu-uniapp-plan ~/.claude/skills/` |

### AI 引导话术

安装到这一步时，请询问用户：

```
Skill 文件可以让我直接从蓝湖设计稿生成对应平台的 UI 代码。
目前支持以下平台，你需要安装哪些？（可多选，只装用得到的就行）

1. Jetpack Compose（Android）
2. Android XML
3. Flutter
4. React Native
5. SwiftUI（iOS）
6. Vue 3
7. HTML + CSS
8. uni-app

请告诉我编号，例如 "1, 3" 表示安装 Compose 和 Flutter。
```

根据用户选择，只复制对应的 Skill 目录。

### 安装后使用示例

```
/lanhu-compose-plan https://lanhuapp.com/web/#/item/project/detailDetach?...&image_id=xxx
```

### 其他客户端

参考对应客户端的 Skill/Plugin 配置方式，将 `skills/` 目录下对应平台的 `SKILL.md` 文件导入即可。

### 可用的 Skill

| Skill 名称 | 输出平台 |
|------------|----------|
| `lanhu-compose-plan` | Jetpack Compose |
| `lanhu-xml-plan` | Android XML |
| `lanhu-flutter-plan` | Flutter |
| `lanhu-rn-plan` | React Native |
| `lanhu-swiftui-plan` | SwiftUI |
| `lanhu-vue-plan` | Vue 3 |
| `lanhu-html-plan` | HTML + CSS |
| `lanhu-uniapp-plan` | uni-app |

---

## 🍪 Cookie 获取简要步骤

1. 打开 https://lanhuapp.com 并登录
2. 按 `F12` 打开开发者工具
3. 切换到 **Network** 标签
4. 刷新页面（按 F5）
5. 点击任意请求，找到 **Request Headers** 下的 **Cookie**
6. 复制整个 Cookie 值，写入 `cookie` 文件

> 📖 详细图文教程参考 [GET-COOKIE-TUTORIAL.md](GET-COOKIE-TUTORIAL.md)

---

## 🤖 AI 自动化安装能力

### AI 可以做的
- ✅ 执行命令下载项目
- ✅ 创建虚拟环境、安装依赖
- ✅ 修改 AI 客户端配置文件
- ✅ 复制 Skill 文件到对应目录
- ✅ 验证安装是否成功

### 需要用户配合的
- ❌ 获取蓝湖 Cookie（浏览器安全限制，需手动操作）
- ❌ 登录蓝湖账号

---

## ✅ 验证安装成功

配置完成后，重启 AI 客户端，然后尝试：

```
帮我看看这个蓝湖设计稿：https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx
```

如果 AI 能正常返回设计图列表，说明安装成功。

---

## 🆘 常见问题

### Q: Cookie 过期了怎么办？
重新登录蓝湖网页版，按上述步骤获取新 Cookie，覆盖写入 `cookie` 文件，重启 AI 客户端即可。

### Q: 提示找不到 run_lanhu_mcp_stdio.sh？
检查配置中的路径是否为**绝对路径**，例如 `/Users/yourname/lanhu-mcp/run_lanhu_mcp_stdio.sh`。

### Q: Windows 下 bash 命令不可用？
Windows 用户推荐使用 Git 自带的 bash，将配置中的 `command` 改为 Git 安装目录下的 `bash.exe` 路径，例如 `D:\\Git\\bin\\bash.exe`，即可直接使用 `.sh` 脚本。

也可以使用 `cmd` 配合项目中的 `run_lanhu_mcp_stdio.bat` 脚本：
```json
{
  "command": "cmd",
  "args": ["/c", "C:\\绝对路径\\lanhu-mcp\\run_lanhu_mcp_stdio.bat"]
}
```
