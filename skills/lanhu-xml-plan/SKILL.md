---
name: lanhu-xml-plan
description: 输入蓝湖设计图详情 URL（含 image_id），使用 lanhu MCP image_id 精确链路输出传统 Android XML（annotations 直出 dp，schema 仅失败兜底，drawable-nodpi 统一落盘；缺失 dp_xx 基线时自动从 skill assets 整套补齐 7 套 dimens）。
---

# 蓝湖 → Android XML（image_id 直连 + annotations(dp) 主路径 + schema 兜底）

## Skill 执行优先级（硬门禁）

当用户消息显式包含 `$lanhu-xml-plan`（或明确点名本 skill）时，必须执行以下规则：

1. **本 skill 规则最高优先级**：
    - 禁止回退到通用转换文档（例如 `ai/ui.md`、`ai/base-ui-convert-rules.md`）作为主流程。
    - 禁止输出“按设计图视觉比例落地”这类非本 skill 数据链路结论。
2. **先协议、后改文件**：
    - 在完整输出“阶段 1 + 阶段 2（A/B/C/D）”之前，禁止修改项目代码文件。
3. **未满足契约即失败**：
    - 未按约定输出 A) 审计区，视为未执行本 skill。
    - 触发时必须输出：`FAIL_FAST: SKILL_CONTRACT_VIOLATION` 并停止。

## 输入格式（从用户消息解析）

支持任意一种：

- 只给一行蓝湖 URL
- 或 key=value 多行：
    - `LANHU_URL=...`
    - `HOST_ACTIVITY=...`（可选）
    - `HOST_FRAGMENT=...`（可选）
    - `PRESENTATION=auto|inline|fragment|dialog|bottom_sheet|popup|activity|dialog_activity`

### 输入硬要求

- `LANHU_URL` 必须是设计图详情链接并包含 `image_id`（`detailDetach?...&image_id=...`）。
- 若缺少 `LANHU_URL`：仅提示补充后停止。
- 若缺少 `image_id`：`FAIL_FAST: IMAGE_ID_MISSING_IN_URL`。

## 必须使用的 MCP 工具（主路径）

必须调用（禁止无工具猜测）：

- `lanhu_get_ai_analyze_design_result(url, image_ids)`
- `lanhu_get_design_annotations(url, image_id)`
- `lanhu_get_design_slices(url, image_id)`

必要时（仅当链接为 PRD/原型文档且包含 `docId`）：

- `lanhu_get_pages`
- `lanhu_get_ai_analyze_page_result`
- `lanhu_resolve_invite_link`

若 lanhu MCP 不可用：提示用户先启动 lanhu-mcp 并确保 Codex 可见，然后停止。

## URL 与工具路由（强制）

1. 设计稿 URL（`/detailDetach` 且含 `image_id`，不含 `docId`）：
    - 仅走 image_id 精确链路：
      `lanhu_get_ai_analyze_design_result(image_ids)` -> `lanhu_get_design_annotations(image_id)` -> `lanhu_get_design_slices(image_id)`
    - 禁止通过 `design_name/design_names` 选择画板。
    - 禁止为“筛选画板”调用 `lanhu_get_designs`。
2. PRD/原型 URL（含 `docId`，通常为 `/product`）：
    - 才允许调用：`lanhu_get_pages` / `lanhu_get_ai_analyze_page_result`
3. 邀请链接（`/link/#/invite?sid=...`）：
    - 先调用 `lanhu_resolve_invite_link`，再按上面规则选择工具链

## 数据源策略（强制）

### 主路径数据源（默认）

- 第一优先：`lanhu_get_design_annotations`（结构化标注，`unit=dp`）
- 第二优先：`lanhu_get_design_slices(..., image_id)` 的 metadata（仅补充样式/资源信息）
- `lanhu_get_ai_analyze_design_result(..., image_ids)` 仅用于视觉核对与阶段 1 简述，不参与尺寸计算

### 几何与测量来源（主路径）

- 元素坐标与尺寸：`annotations.layers`（已是整数 dp）
- 自动测量优先使用：`annotations.measurements`
    - `text_container_paddings`
    - `icon_text_distances`
    - `nearest_neighbors`
- 当 measurements 缺项时，才回退到图层几何关系推导间距

### 尺寸与单位规则（主路径）

- `annotations.unit = dp` 时：
    - 位置/宽高/圆角/边框/阴影等数值直接映射到 `@dimen/dp_*`
    - 不做 `411/750` 二次换算
- 文本尺寸：
    - `text.font_size` 与 `text.line_height` 采用同值映射到 `@dimen/sp_*`
    - 不做二次换算

### 禁止项

- 禁止使用 OCR
- 禁止无来源猜测文本字号或间距
- 禁止在主路径中再次执行 `px -> dp` 缩放

## 网页 schema 兜底链路（仅失败时启用）

仅当以下任一条件成立时触发兜底：

- `lanhu_get_design_annotations` 调用失败
- annotations 缺关键字段（`unit/layers/measurements`）
- `lanhu_get_design_slices` 调用失败且无法获取关键资源信息
- `lanhu_get_ai_analyze_design_result` 调用失败（仅影响阶段 1 语义描述时可降级为 `EMPTY`）

触发兜底后：

- 启用旧 schema 链路（cookie + `project/image` + `store_schema_revise`）
- 仅在此链路使用换算：`round(px * 411 / 750)`
- A) 审计区必须标注：`source_mode=web_schema_fallback` 与 `fallback_reason`

### 兜底 cookie 约束

- 固定路径：`COOKIE_PATH=~/.codex/mcp/lanhu-mcp/cookie`
- 运行时读取该文件作为 `Cookie` 请求头
- 日志与输出中禁止回显 cookie 内容

## 硬门禁（强制）

1. URL 缺少 `image_id`：
    - `FAIL_FAST: IMAGE_ID_MISSING_IN_URL`
2. 主路径 annotations 缺关键结构且兜底失败：
    - `FAIL_FAST: PRIMARY_AND_FALLBACK_BOTH_FAILED`
3. 进入兜底后 cookie 文件不存在或为空：
    - `FAIL_FAST: COOKIE_FILE_MISSING`
4. 进入兜底后预检失败或返回非成功 code：
    - `FAIL_FAST: COOKIE_INVALID_OR_EXPIRED`
5. 进入兜底后 schema 拉取失败：
    - `FAIL_FAST: SCHEMA_FETCH_FAILED`
6. 进入兜底后 schema 解析失败：
    - `FAIL_FAST: SCHEMA_PARSE_FAILED`

默认一律硬失败，禁止静默降级为估算模式。

## 硬约束（必须严格执行）

1) **仅 XML**：禁止 Compose；UI 禁止 Kotlin 代码绘制（不输出 Kotlin UI）。

2) **禁止硬编码 dp/sp**：任何输出 XML 中不得出现字面量 dp/sp（如 `16dp`、`14sp`）。
   - dp 只能引用：`@dimen/dp_N` 或 `@dimen/dp_Nd5`
   - sp 只能引用：`@dimen/sp_N` 或 `@dimen/sp_Nd5`
   - `0dp` 必须用：`@dimen/dp_0`（包括 ConstraintLayout 的 match-constraints）

3) **dimen 命名视为真实单位**：
   - `5dp -> @dimen/dp_5`，`5.5dp -> @dimen/dp_5d5`
   - `14sp -> @dimen/sp_14`

4) **dimen 基线资源约束**：
   - 真正写入 Android 工程文件前，必须先检查目标模块的 `res/values*/dimens.xml` 是否具备可用 `dp_*` 基线。
   - 本 skill 只允许使用当前目录下的 7 套 asset 基线：
     `assets/values/dimens.xml`、
     `assets/values-sw390dp/dimens.xml`、
     `assets/values-sw411dp/dimens.xml`、
     `assets/values-sw420dp/dimens.xml`、
     `assets/values-sw440dp/dimens.xml`、
     `assets/values-sw600dp/dimens.xml`、
     `assets/values-sw840dp/dimens.xml`
   - 若目标模块缺少任一目录、缺少任一 `dimens.xml`、或现有文件中不存在可解析的 `name="dp_..."` 资源（例如 `dp_0`），统一视为 `dimen_baseline=missing`。
   - `dimen_baseline=missing` 时，必须一次性同步上述 7 个目录，禁止只复制其中一部分目录。
   - 目标 `dimens.xml` 不存在时：直接复制对应 asset 文件。
   - 目标 `dimens.xml` 已存在时：保留项目现有同名 `<dimen name="...">` 值，仅将 asset 中缺失的 name 追加到现有文件末尾。
   - 追加范围是整份 `dimens.xml` 的缺项，包含 `dp_*`、`sp_*`、`ndp_*`；禁止只补 `dp_*` 或只补部分目录。
   - 若 7 套 asset 中任一目录或 `dimens.xml` 缺失、不可读或内容不完整：`FAIL_FAST: DIMEN_ASSET_SET_INCOMPLETE`

5) **主路径禁止换算**：
   - 当 `annotations.unit=dp` 时，禁止再次执行 `411/750` 缩放
   - 仅 `web_schema_fallback` 可使用：`round(px * 411 / 750)`

6) **TextView 行距基础约束（全量生效）**：
   - 所有 `TextView` 必须输出：`android:includeFontPadding="false"`
   - 所有 `TextView` 必须输出：`android:lineSpacingExtra="@dimen/dp_0"`
   - 单行文本：`android:lineSpacingMultiplier="1"`
   - 多行文本：`android:lineSpacingMultiplier` 可按自动测量结果调整（无测量时默认 `1`）
   - 默认（`minSdk < 28`）禁止输出：`android:lineHeight`、`android:fallbackLineSpacing`
   - 仅当明确 `minSdk >= 28` 时，才允许额外输出上述属性

7) **icon 来源约束**：
   - 除“明显纯色填充的基础几何形（无渐变/阴影/描边/纹理）”外，icon 不得手动画 vector。
   - 常规 icon 必须直接使用 `lanhu_get_design_slices(url, image_id)` 返回资源。

8) **切图格式与目录约束**：
   - 切图默认输出 `webp`（透明或质量异常可回退 `png`，并在规格表标注原因）
   - 所有栅格切图（`webp/png`）统一落盘到：`res/drawable-nodpi/`
   - 仅 XML drawable（`<shape> <vector> <selector> <layer-list> <ripple> ...`）放置在：`res/drawable/`

9) **资源命名**：`ic_xxx` / `img_xxx` / `bg_xxx`（语义化，禁止 `image_123`）。

10) **字体/颜色（可读性优先）**：
   - 禁止为单个控件创建 style
   - 字体属性完全相同在同一界面出现 `>=2` 次才允许抽成 `@style/Text.*`，否则一律 inline
   - 颜色默认引用现有 `@color/...`；同色 `>=3` 次或全局语义色才建议归并 token

## 间距计算规则（强制）

1. **必须使用 annotations 绝对坐标计算间距**：
   - 垂直间距 = `next_element.position.y - (current_element.position.y + current_element.size.height)`
   - 水平间距 = `next_element.position.x - (current_element.position.x + current_element.size.width)`
   - 禁止使用"大约"、"看起来像"等估算方式
2. **优先使用 `measurements.sibling_spacings`**（如果可用）：
   - 直接读取 `gap_to_next` 作为 `android:layout_marginTop/Start` 等
   - 当 `layout_direction = horizontal` → 使用 `LinearLayout(horizontal)` 或 `ConstraintLayout` 水平链
   - 当 `layout_direction = vertical` → 使用 `LinearLayout(vertical)` 或 `ConstraintLayout` 垂直链
   - 当 `layout_direction = stack` → 使用 `FrameLayout`
3. **禁止用通用系统适配方案替代设计稿间距**：
   - 禁止用固定值替代 annotations 中的精确间距

## 层级树消费规则（强制）

1. **当 `layout_tree` 可用且有层级时，必须按树结构组织布局**：
   - 树的每个 group 节点对应一个容器 ViewGroup
   - 子节点按 `children` 数组顺序排列
   - 禁止忽略树结构而自行猜测层级
2. **当 `layout_tree` 不可用或扁平时**，从 `layer_path` 和 `parent_name` 重建
3. **当以上均不可用时**，从绝对坐标推断

## 边框与阴影消费规则（强制）

1. **边框**：读取 `style.borders_parsed[]`
   - `color` → 边框颜色
   - `width` → 边框宽度（已转 dp）
   - 输出：`<stroke android:width="..." android:color="..." />`
2. **阴影**：读取 `style.shadows[]`
   - 输出：`android:elevation="..."`
3. **圆角**：`border_radius` 和 `border_radius_detail_raw` 已转为 dp
   - 禁止对圆角值再次执行缩放
   - 输出：`<corners android:radius="..." />` 或分角 `<corners android:topLeftRadius="..." .../>`

## 安全区与系统栏

System insets should NOT be used to replace design-specified spacing. Only use system insets for areas not covered by the design.

## 输出契约（严格）

- **阶段 1**：只输出“选中画板 + 默认承载方式 + 预期产出文件清单”。
  - 不输出 XML
  - 不输出 slices 列表
  - 不输出接入/伪代码
- **阶段 2**：只输出「A) 审计区 + B) 规格表 + C) XML 文件内容 + D) 资源清单」。
  - A 必须先于 B/C/D 输出，且字段完整
  - 不输出接入指引/验收说明

### A) 审计区强制字段（缺一即失败）

必须包含以下字段，缺任意一项时立即：
`FAIL_FAST: SKILL_CONTRACT_VIOLATION`

- `tool_route=design_chain|prd_chain`
- `mcp_calls`
- `selection_key=image_id`
- `selected_image_id`
- `source_mode=mcp_annotations_primary|web_schema_fallback`
- `unit=dp|px`
- `conversion_applied=true|false`
- `dimen_baseline=existing|missing`
- `text_source_priority`
- `data_source=text/icon/spacing=annotations|dds_schema`
- `fallback_reason`（仅兜底时必填）

---

## 阶段 1（定位/选中/默认承载）

1. 解析 `LANHU_URL`，提取 `image_id`
2. 不调用 `lanhu_get_designs` 进行筛选；直接以该 `image_id` 作为唯一目标
3. 调用 `lanhu_get_ai_analyze_design_result(url, image_ids=[image_id])` 获取视觉核对信息（失败可记 `EMPTY`）
4. 默认 `PRESENTATION` 规则：
   - `bottom_sheet`: 含“底部弹窗/底部弹出/bottom sheet”
   - `dialog`: 含“弹窗/对话框/提示/确认/dialog”
   - `popup`: 含“气泡/悬浮/tooltip/pop”
   - `dialog_activity`: 含“半屏/透明/浮层Activity”
   - `activity`: 明确“独立整屏页面/导航入口/深链页”
   - 否则 `fragment`
5. 阶段 1 输出：
   - `SELECTED: image_id=... name=... size_dp=...`
   - `PRESENTATION: <value>（一句理由）`
   - `FILES: 阶段2将生成的文件名`

---

## 阶段 2（审计 + 规格 + XML + 资源）

前置：`selected_image_id` 已确定。

1. 调用 `lanhu_get_design_annotations(url, image_id)` 获取结构化标注（主路径）
2. 校验 `unit` 与关键字段（`layers/measurements`）
3. 调用 `lanhu_get_design_slices(url, image_id)` 获取切图与资源信息
4. 主路径生成规则：
   - 几何值按 dp 直出（不换算）
   - 文本值同值映射到 sp
   - 间距优先使用 measurements，缺项时回退几何关系
5. 若步骤 1~3 任一失败或缺关键字段，触发 `web_schema_fallback`
6. 输出 A) 审计区（必须完整）
7. 输出 B) 规格表（<=3层组件树）
8. 输出 C) XML 文件内容（仅 XML）
9. 输出 D) 资源清单（仅列表）

## 改文件前的资源预检与同步（仅在阶段 2 完整输出之后执行）

仅当当前任务包含“把 XML/资源真正写入 Android 工程”时执行以下规则：

1. 先定位本次 XML 要写入的目标 Android 模块。
2. 模块定位优先级：
   - 若用户提供 `HOST_ACTIVITY` 或 `HOST_FRAGMENT`，优先定位其所在模块。
   - 否则，按本次计划写入的布局 XML / drawable / drawable-nodpi 所属模块定位。
   - 若工程内存在多个候选模块且无法唯一判断，停止并要求用户指定；禁止猜测目标模块。
3. 在目标模块中依次检查以下 7 个路径：
   - `res/values/dimens.xml`
   - `res/values-sw390dp/dimens.xml`
   - `res/values-sw411dp/dimens.xml`
   - `res/values-sw420dp/dimens.xml`
   - `res/values-sw440dp/dimens.xml`
   - `res/values-sw600dp/dimens.xml`
   - `res/values-sw840dp/dimens.xml`
4. 若 7 个文件全部存在，且每个文件都含可解析的 `dp_*` 资源，则记为 `dimen_baseline=existing`，`dimens_sync=skip`，不修改 `dimens` 文件。
5. 若任一目录缺失、任一文件缺失，或任一文件缺少 `dp_*` 基线，则记为 `dimen_baseline=missing`，并按 7 套 asset 逐文件执行整套同步：
   - 7 个目标文件全部不存在：`dimens_sync=copy`
   - 7 个目标文件全部已存在但需要补条目：`dimens_sync=merge`
   - 同时存在“部分文件缺失 + 部分文件需补条目”：`dimens_sync=copy+merge`
6. 完成 `dimens` 同步后，才允许真正写入布局 XML、drawable 和切图资源。

### B) 规格表字段（主路径）

- `component | view_type | parent | strategy`
- `position_dp(x,y) | size_dp(w,h) | @dimen/dp_*`
- `font_size_dp -> @dimen/sp_* | line_height_dp -> @dimen/sp_* | letter_spacing`
- `text_padding(measurements) | icon_text_distance | nearest_neighbor`
- `asset_format(webp/png) | asset_output_dir(drawable-nodpi/drawable) | asset`

### D) 资源清单最少字段

- `dimens_sync=skip|copy|merge|copy+merge`
- `dimens_source=skill_assets`
- `dimens_targets=res/values/dimens.xml,res/values-sw390dp/dimens.xml,res/values-sw411dp/dimens.xml,res/values-sw420dp/dimens.xml,res/values-sw440dp/dimens.xml,res/values-sw600dp/dimens.xml,res/values-sw840dp/dimens.xml`
- `asset_format(webp/png) | asset_output_dir(drawable-nodpi/drawable) | asset`

### 兜底路径补充字段（仅 fallback）

- `scale_formula=411/750`
- `conversion_rule=round(px * 411 / 750)`
- `schema_version_id`
- `schema_source_url`

除 A/B/C/D 外不要输出任何内容。
