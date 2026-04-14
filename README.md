<div align="center">

# 🎨 Lanhu MCP Server Enhanced

**蓝湖 MCP 服务器增强版 — 设计标注提取 + 多平台 UI 代码生成**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

</div>

> 本项目基于 [dsphper/lanhu-mcp](https://github.com/dsphper/lanhu-mcp) 开源项目修改和扩展，感谢原作者 [@dsphper](https://github.com/dsphper) 的出色工作。
>
> 原项目已提供完整的蓝湖 MCP 能力（需求文档分析、设计稿查看、切图提取、团队留言板等），**请先前往 [原项目](https://github.com/dsphper/lanhu-mcp) 了解基础功能。**
>
> 本仓库在此基础上新增了以下功能。

### 💡 推荐安装方式：让 AI 帮你装

直接把下面这段话发给你的 AI 助手（Claude Code / Cursor / Windsurf 等），AI 会自动完成所有安装和配置：

```
请阅读 https://github.com/dj931567261/lanhu-mcp 项目中的 ai-install-guide.md 文件，
按照里面的步骤帮我安装和配置这个蓝湖 MCP 服务器。
```

或者如果你已经克隆了项目：

```
请阅读当前项目下的 ai-install-guide.md，帮我完成安装和配置。
```

AI 会自动：创建虚拟环境 → 安装依赖 → 引导你获取 Cookie → 配置 AI 客户端 → 安装 Skill 文件

> 📖 手动安装参考 [AI 助手安装指南](ai-install-guide.md)

### ⚠️ 连接方式差异

原项目使用 **HTTP SSE** 方式连接（`http://localhost:8000/mcp`），本项目改为 **stdio** 方式，直接通过脚本启动，无需单独运行服务。

**AI 客户端配置示例（Claude Code / Cursor / Windsurf 等）：**
```json
{
  "mcpServers": {
    "Lanhu-mcp": {
      "command": "bash",
      "args": ["/path/to/lanhu-mcp/run_lanhu_mcp_stdio.sh"],
      "env": {
        "LANHU_MCP_USER_NAME": "YourName",
        "LANHU_MCP_USER_ROLE": "Developer"
      }
    }
  }
}
```

> Cookie 配置：将蓝湖 Cookie 写入项目根目录的 `cookie` 文件，或设置环境变量 `LANHU_COOKIE`。获取方式参考 [Cookie 获取教程](GET-COOKIE-TUTORIAL.md)。

### 🎯 使用方式

安装完成后，在 AI 对话中使用对应平台的 Skill 名称 + 蓝湖设计图链接，即可生成 UI 代码：

```
/lanhu-compose-plan https://lanhuapp.com/web/#/item/project/detailDetach?pid=xxx&image_id=xxx
帮我实现一下这个页面，注意复用底部的导航栏，输出到 app/src/main/java/com/example/ui/ 目录下
```

你可以在消息中补充任何额外要求，例如：
- 复用已有组件：`注意复用底部的导航栏和顶部状态栏`
- 指定输出目录：`输出到 src/pages/ 目录下`
- 指定页面行为：`这是一个底部弹窗，不是整屏页面`
- 数据对接：`列表数据从 ViewModel 获取，这里只写 UI`

不同平台使用对应的 Skill 名称：

| 命令 | 平台 |
|------|------|
| `/lanhu-compose-plan` | Jetpack Compose |
| `/lanhu-xml-plan` | Android XML |
| `/lanhu-flutter-plan` | Flutter |
| `/lanhu-rn-plan` | React Native |
| `/lanhu-swiftui-plan` | SwiftUI |
| `/lanhu-vue-plan` | Vue 3 |
| `/lanhu-html-plan` | HTML + CSS |
| `/lanhu-uniapp-plan` | uni-app |

---

## 🆕 新增功能概览

| 功能 | 说明 |
|------|------|
| **设计标注数据（annotations）** | 精确提取图层坐标、尺寸、颜色、字体、间距、圆角等 dp 级参数 |
| **布局分析** | 兄弟间距、布局方向检测、层级树、最近邻关系 |
| **设计图分组与搜索** | 按分组查看、按关键词搜索设计图 |
| **Skill 代码生成（8 平台）** | 配合 annotations 数据，约束 AI 生成高还原度 UI 代码 |

---

## 📐 设计标注数据（annotations）

新增 `lanhu_get_design_annotations` 工具，从蓝湖设计图中提取结构化标注数据，自动转换为 dp 单位。

### 返回数据

- **图层数据**：每个图层的坐标（x, y）、尺寸（width, height）、颜色、渐变、透明度、圆角
- **文本属性**：字体、字号、字重、行高、字间距、颜色、对齐方式
- **样式解析**：边框（颜色/宽度/对齐）、阴影、渐变（支持 Figma 和 Sketch 两种格式）
- **自动缩放**：根据设计稿宽度自动推断 px→dp 缩放系数（720px→0.5, 1080px→0.33）

### 布局分析（measurements）

| 字段 | 说明 |
|------|------|
| `sibling_spacings` | 同级元素间距 + 布局方向检测（horizontal / vertical / stack） |
| `layout_tree` | 图层层级树结构（Figma 用 path 构建，Sketch 用几何包含推断） |
| `nearest_neighbors` | 最近邻元素关系（已排除父子包含关系） |
| `text_container_paddings` | 文本与容器的内边距 |
| `icon_text_distances` | 图标与文本的距离 |

---

## 🔍 设计图分组与搜索

| 工具 | 说明 |
|------|------|
| `lanhu_get_designs_by_sector` | 按分组名称查看设计图（支持精确/模糊匹配） |
| `lanhu_search_designs` | 按关键词搜索设计图名称 |

---

## 🧩 Skill 文件（8 个平台）

内置 8 个平台的 Skill 文件（位于 `skills/` 目录），配合 `lanhu_get_design_annotations` 返回的标注数据，约束 AI 生成高还原度 UI 代码。

### 支持的平台

| Skill | 输出格式 |
|-------|----------|
| `lanhu-compose-plan` | Jetpack Compose |
| `lanhu-xml-plan` | Android XML |
| `lanhu-flutter-plan` | Flutter Dart |
| `lanhu-rn-plan` | React Native TSX |
| `lanhu-swiftui-plan` | SwiftUI |
| `lanhu-vue-plan` | Vue 3 SFC |
| `lanhu-html-plan` | HTML + CSS |
| `lanhu-uniapp-plan` | uni-app |

### 安装 Skill

将 `skills/` 目录下的文件复制到 AI 客户端的 Skill 目录：

**Claude Code：**
```bash
cp -r skills/lanhu-*-plan ~/.claude/skills/
```

其他 AI 客户端参考对应的 Skill/Plugin 配置方式，将 `SKILL.md` 文件导入即可。

### 使用方式

安装 Skill 后，给 AI 发送蓝湖设计图链接即可触发：

```
/lanhu-compose-plan https://lanhuapp.com/web/#/item/project/detailDetach?...&image_id=xxx
```

AI 会自动：
1. 识别设计图，确定页面类型和文件结构
2. 获取 annotations 精确标注数据 + 切图资源
3. 按 Skill 规则生成对应平台的 UI 代码

### Skill 核心约束

- **间距**：必须使用 annotations 绝对坐标差值计算，禁止估算
- **颜色/字体**：必须使用 annotations 提供的精确值
- **圆角**：annotations 返回值已转 dp，禁止再缩放
- **透明度**：必须读取 `style.opacity` 并应用到组件
- **切图**：icon/图片必须使用 `lanhu_get_design_slices` 返回的资源，禁止手绘
- **沉浸式适配**（Compose）：Header 高度 = 设计稿高度 + 动态状态栏高度，内部用 `statusBarsPadding()` 处理

---

## 📁 项目结构

```
lanhu-mcp/
├── lanhu_mcp_server.py        # MCP 服务端主文件
├── run_lanhu_mcp_stdio.sh     # MCP 启动脚本
├── requirements.txt           # Python 依赖
├── pyproject.toml             # 项目配置
├── config.example.env         # 环境变量示例
├── cookie                     # 蓝湖 Cookie（需自行填写，勿提交）
├── skills/                    # Skill 文件
│   ├── lanhu-compose-plan/
│   ├── lanhu-xml-plan/
│   ├── lanhu-flutter-plan/
│   ├── lanhu-rn-plan/
│   ├── lanhu-swiftui-plan/
│   ├── lanhu-vue-plan/
│   ├── lanhu-html-plan/
│   └── lanhu-uniapp-plan/
├── tests/                     # 测试文件
├── LICENSE
├── README.md
├── README_EN.md
├── GET-COOKIE-TUTORIAL.md     # Cookie 获取教程
└── ai-install-guide.md        # AI 客户端安装指南
```

---

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)

<!-- Last checked: 2026-04-14 09:07 -->
