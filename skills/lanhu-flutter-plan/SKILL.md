---
name: lanhu-flutter-plan
description: 输入蓝湖设计图详情 URL（含 image_id），使用 lanhu MCP image_id 精确链路输出 Flutter Dart Widget 规划；annotations 为主路径，单位与圆角归一在 skill 内完成，schema 仅失败兜底，资源统一落盘到 assets/lanhu/<screen>/ 并补齐 pubspec 资产声明。
---

# 蓝湖 → Flutter Dart Widget（image_id 直连 + annotations 主路径 + skill 归一）

## Skill 执行优先级（硬门禁）

当用户消息显式包含 `$lanhu-flutter-plan`（或明确点名本 skill）时，必须执行以下规则：

1. **本 skill 规则最高优先级**：
   - 禁止回退到通用 UI 转换文档作为主流程。
   - 禁止输出 XML、Compose、React Native、SwiftUI。
   - 禁止输出“按视觉估算实现”这类脱离本 skill 数据链路的结论。
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
  - `PRESENTATION=auto|inline|page|dialog|bottom_sheet|popup|fullscreen_dialog`

### 输入硬要求

- `LANHU_URL` 必须是设计图详情链接并包含 `image_id`（`detailDetach?...&image_id=...`）。
- 为兼容既有调用协议，保留 `HOST_ACTIVITY` / `HOST_FRAGMENT` 字段名；在 Flutter 场景中仅作为宿主页面或挂载点线索，不生成 Android 代码。
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
   - 先调用 `lanhu_resolve_invite_link`，再按上面规则选择工具链。

## 数据源策略（强制）

### 主路径数据源（默认）

- 第一优先：`lanhu_get_design_annotations`
- 第二优先：`lanhu_get_design_slices(..., image_id)` 的 metadata（仅补充样式、资源、导出格式）
- `lanhu_get_ai_analyze_design_result(..., image_ids)` 仅用于视觉核对与阶段 1 简述，不参与尺寸计算

### 几何与测量来源（主路径）

- 元素坐标与尺寸：`annotations.layers`
- 自动测量优先使用：`annotations.measurements`
  - `text_container_paddings`
  - `icon_text_distances`
  - `nearest_neighbors`
- 当 measurements 缺项时，才回退到图层几何关系推导间距

### 单位与圆角归一规则（主路径）

- `annotations.style.border_radius` 是优先可消费圆角值：
  - 单值圆角输出：`BorderRadius.circular(...)`
  - 分角圆角输出：`BorderRadius.only(...)`
  - 仅当 `annotations.style.border_radius` 缺失时，才允许从图层样式补推
- 所有 `*_raw` 字段都视为原始源数据：
  - 禁止直接输出到 Flutter 代码
  - 必须先由 skill 完成单位归一、结构归一，再写入 Widget
- `annotations.unit = dp` 时：
  - 位置、宽高、边框、阴影、间距、圆角直接视为 Flutter 逻辑像素
  - 文本尺寸输出为归一后的 Flutter `double`
  - 禁止再次执行 `411/750` 缩放
- 文本规则：
  - `font_size` -> `TextStyle.fontSize`
  - `line_height` 先归一为绝对值，再转换为 `TextStyle.height = lineHeight / fontSize`
  - `letter_spacing` 只能输出归一后的值

### 禁止项

- 禁止使用 OCR
- 禁止无来源猜测文本字号、间距、圆角或阴影
- 禁止在主路径中再次执行 `px -> dp` 缩放
- 禁止把 `*_raw`、`px`、未归一的 schema 原值直接塞进 Dart Widget

## 跨平台高保真约束（统一生效）

1. **测量优先**：
   - 间距、内边距、图文距离、对齐关系优先消费 `annotations.measurements`
   - 仅 measurements 缺项时才允许回退到图层几何关系
   - 禁止用“看起来差不多”替代真实测量
2. **复杂视觉元素优先切图**：
   - 关闭按钮、手势、优惠券票面、不规则卡片、插画、纹理、复杂渐变、复杂阴影组合等元素，优先直接使用 `lanhu_get_design_slices`
   - 仅明显纯色基础几何形且原生样式或组件能稳定逼近蓝湖效果时，才允许直接原生绘制
   - 若原生绘制无法稳定达到接近蓝湖结果，必须回退到 slices
3. **禁止近似替代真实资源**：
   - 同一视觉元素禁止混用“手画近似版”和“真实切图版”
   - 已存在可用 slice 时，禁止为了省事改成低保真近似版本
4. **文本 fidelity**：
   - 必须保留文本层级、强调态、弱化态、删除线、换行策略与截断策略
   - 长文本必须给出溢出策略，旧价/辅助态不得静默省略
5. **适配策略统一**：
   - 禁止整页或整树缩放
   - 优先”主内容限宽 + 居中 + 安全区 + 键盘避让 + 溢出滚动”
   - 底部主按钮、BottomSheet 操作区不得落到安全区外或被键盘遮挡
   - SafeArea should NOT be used to replace design-specified spacing. Only use SafeArea for areas not covered by the design.
6. **绝对定位收敛**：
   - 仅角标、浮层锚点、重叠装饰、悬浮手势等场景允许绝对定位或局部偏移
   - 主信息流禁止用绝对定位拼页面
7. **图层透明度（强制）**：
   - 必须读取 `annotations.layers[].style.opacity`
   - 当 `style.opacity` 不为 null（即 < 1.0）时，必须在对应组件上应用平台对应的透明度属性
   - `style.opacity` 影响整个图层，如果是容器背景色，应用到背景色的 alpha 通道
8. **审计与资源清单补充**：
   - A) 审计区除必填字段外，追加 `asset_strategy=native_only|native_plus_slice|slice_priority`
   - A) 审计区除必填字段外，追加 `adaptation_strategy=limit_width|safe_area|ime_avoid|scroll_guard|mixed`
   - D) 资源清单必须说明哪些元素使用原生绘制，哪些元素使用 slices，以及原因

## 网页 schema 兜底链路（仅失败时启用）

仅当以下任一条件成立时触发兜底：

- `lanhu_get_design_annotations` 调用失败
- annotations 缺关键字段（`unit/layers/measurements`）
- `lanhu_get_design_slices` 调用失败且无法获取关键资源信息
- `lanhu_get_ai_analyze_design_result` 调用失败（仅影响阶段 1 语义描述时可降级为 `EMPTY`）

触发兜底后：

- 启用旧 schema 链路（优先复用当前 Lanhu MCP 运行环境中的 `LANHU_COOKIE`，再按 `project/image` + `store_schema_revise` 执行）
- 仅在此链路使用换算：`round(px * 411 / 750)`
- 所有 schema 原值先落入 `*_raw`，再完成归一后才能输出到 Flutter 代码
- A) 审计区必须标注：`source_mode=web_schema_fallback` 与 `fallback_reason`

### 兜底 cookie 约束

- 第一优先：复用当前 Lanhu MCP 进程已有的 `LANHU_COOKIE`
- 若当前任务必须从文件读取 cookie，必须先检查当前 MCP 启动脚本或由用户显式提供路径，禁止写死历史路径
- 仅当环境变量缺失且已确认文件路径时，才允许读取该文件作为 `Cookie` 请求头
- 日志与输出中禁止回显 cookie 内容

## 硬门禁（强制）

1. URL 缺少 `image_id`：
   - `FAIL_FAST: IMAGE_ID_MISSING_IN_URL`
2. 主路径 annotations 缺关键结构且兜底失败：
   - `FAIL_FAST: PRIMARY_AND_FALLBACK_BOTH_FAILED`
3. 进入兜底后未获取到可用 cookie（`LANHU_COOKIE` 缺失，且未提供可读的 cookie 文件路径）：
   - `FAIL_FAST: COOKIE_SOURCE_UNAVAILABLE`
4. 进入兜底后预检失败或返回非成功 code：
   - `FAIL_FAST: COOKIE_INVALID_OR_EXPIRED`
5. 进入兜底后 schema 拉取失败：
   - `FAIL_FAST: SCHEMA_FETCH_FAILED`
6. 进入兜底后 schema 解析失败：
   - `FAIL_FAST: SCHEMA_PARSE_FAILED`

默认一律硬失败，禁止静默降级为估算模式。

## Flutter 硬约束（必须严格执行）

1. **仅 Dart Widget**：
   - 阶段 2 的代码产出只能是 Dart Widget 文件内容。
   - 禁止输出 XML、Compose、React Native、伪 DSL。
2. **布局组件优先级**：
   - 优先 `SingleChildScrollView` / `Column` / `Row` / `Stack`
   - 仅在常规组件无法覆盖视觉结果时才允许使用 `CustomPainter`
3. **圆角输出规则**：
   - 统一圆角：`BorderRadius.circular(...)`
   - 分角圆角：`BorderRadius.only(...)`
   - 禁止输出未归一的圆角数组或 `*_raw`
4. **资源落盘规则**：
   - 所有切图、图标、背景资源统一放到：`assets/lanhu/<screen>/`
   - 资源命名使用语义化名称，例如：`ic_close.png`、`img_banner.webp`、`bg_card.png`
5. **资源清单覆盖 pubspec**：
   - 阶段 2 的 D) 资源清单必须包含 `pubspec.yaml` 所需资产声明
   - 至少覆盖：`assets/lanhu/<screen>/`
6. **资源使用约束**：
   - 常规资源使用 `Image.asset`
   - 仅明显纯色基础几何形才允许直接用 `Container` / `DecoratedBox` 绘制
   - 若图形复杂到必须自绘，需在规格表与审计区明确说明原因

7. **切图格式约束**：
   - 切图默认输出 `webp`（透明或质量异常可回退 `png`，并在规格表标注原因）
   - 所有栅格切图统一落盘到：`assets/lanhu/<screen>/`
8. **icon / 切图来源约束（强制）**：
   - 除"明显纯色填充的基础几何形（无渐变/阴影/描边/纹理）"外，icon 不得手动用 CustomPaint 绘制
   - 常规 icon 必须直接使用 `lanhu_get_design_slices(url, image_id)` 返回的资源
   - 当 slices 提供了某个区域的完整合成切图（如 `bg`、`编组`、`layer-group` 类型的切图，且面积覆盖该区域 >= 80%），必须优先使用切图 `Image.asset(...)` 作为背景，禁止用 annotations 的纯色/渐变去模拟多层叠加效果
9. **字体/颜色（可读性优先）**：
   - 禁止为单个控件创建额外的 TextStyle 常量
   - 字体属性完全相同在同一界面出现 `>=2` 次才允许抽成共享 TextStyle，否则一律 inline
   - 颜色默认使用文件级常量；同色 `>=3` 次或全局语义色才建议归并到 theme/token

## Flutter UI 适配优化（必须执行）

1. **根布局适配**：
   - 页面根节点优先使用 `Scaffold` + `SafeArea`（SafeArea should NOT be used to replace design-specified spacing; only use SafeArea for areas not covered by the design）
   - 主内容区优先通过 `LayoutBuilder` 读取可用宽度，再结合 `ConstrainedBox(maxWidth: ...)` + `Align` 做限宽居中
   - 禁止整页 `Transform.scale` 适配不同屏宽
2. **滚动与键盘避让**：
   - 只要垂直内容有超出风险，优先使用 `SingleChildScrollView`
   - 输入页、表单页、登录页必须考虑 `MediaQuery.viewInsets.bottom`
   - 底部弹层优先 `isScrollControlled: true` 的适配思路
3. **大屏与横屏策略**：
   - 平板或横屏优先“居中主栏 + 最大宽度约束”，而不是简单拉伸控件宽度
   - 双列布局仅在原始结构允许拆分时才启用，禁止擅自重排核心阅读顺序
4. **弹性布局规则**：
   - 文字区、按钮区、左右结构优先使用 `Expanded` / `Flexible`
   - 标签流、按钮流优先使用 `Wrap`
   - 禁止在主内容区堆大量固定宽 `SizedBox`
5. **文本与图片适配**：
   - 长文本必须给出 `maxLines` / `overflow`
   - 图片必须显式声明 `fit`
   - 比例敏感资源优先补 `AspectRatio`
6. **绝对定位收敛**：
   - 仅重叠卡片、角标、浮层锚点允许 `Stack + Positioned`
   - 主信息流禁止依赖大量 `Positioned`

## 间距计算规则（强制）

1. **必须使用 annotations 绝对坐标计算间距**：
   - 垂直间距 = `next_element.position.y - (current_element.position.y + current_element.size.height)`
   - 水平间距 = `next_element.position.x - (current_element.position.x + current_element.size.width)`
   - 禁止使用"大约"、"看起来像"等估算方式
2. **优先使用 `measurements.sibling_spacings`**（如果可用）：
   - 直接读取 `gap_to_next` 作为 `SizedBox(height/width: gap)`
   - 当 `layout_direction = horizontal` → 使用 `Row`
   - 当 `layout_direction = vertical` → 使用 `Column`
   - 当 `layout_direction = stack` → 使用 `Stack`
3. **禁止用通用系统适配方案替代设计稿间距**：
   - 禁止用 `SafeArea` 替代设计稿中已标注的具体间距
   - 禁止用固定值替代 annotations 中的精确间距

## 层级树消费规则（强制）

1. **当 `layout_tree` 可用且有层级时，必须按树结构组织 Widget**：
   - 树的每个 group 节点对应一个容器 Widget
   - 子节点按 `children` 数组顺序排列
   - 禁止忽略树结构而自行猜测层级
2. **当 `layout_tree` 不可用或扁平时**，从 `layer_path` 和 `parent_name` 重建
3. **当以上均不可用时**，从绝对坐标推断

## 边框与阴影消费规则（强制）

1. **边框**：读取 `style.borders_parsed[]`
   - 输出：`Border.all(color: Color(0xFF...), width: ...)`
2. **阴影**：读取 `style.shadows[]`
   - 输出：`BoxShadow(color: ..., blurRadius: ..., offset: Offset(...))`
3. **圆角**：`border_radius` 和 `border_radius_detail_raw` 已转为 dp
   - 禁止对圆角值再次执行缩放
   - 输出：`BorderRadius.circular(value)` 或 `BorderRadius.only(...)`

## 输出契约（严格）

- **阶段 1**：只输出“选中画板 + 默认承载方式 + 预期产出文件清单”。
  - 不输出 Dart 代码
  - 不输出 slices 列表
  - 不输出接入说明
- **阶段 2**：只输出「A) 审计区 + B) 规格表 + C) Dart Widget 文件内容 + D) 资源清单」。
  - A 必须先于 B/C/D 输出，且字段完整
  - 不输出接入指引、验收说明、状态总结

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
- `dimen_baseline=not_applicable`
- `text_source_priority`
- `data_source=text/icon/spacing=annotations|dds_schema`
- `fallback_reason`（仅兜底时必填）

## 阶段 1（定位/选中/默认承载）

1. 解析 `LANHU_URL`，提取 `image_id`
2. 不调用 `lanhu_get_designs` 进行筛选；直接以该 `image_id` 作为唯一目标
3. 调用 `lanhu_get_ai_analyze_design_result(url, image_ids=[image_id])` 获取视觉核对信息（失败可记 `EMPTY`）
4. 默认 `PRESENTATION` 规则：
   - `bottom_sheet`：含“底部弹窗/底部弹出/bottom sheet”
   - `dialog`：含“弹窗/对话框/提示/确认/dialog”
   - `popup`：含“气泡/悬浮/tooltip/pop”
   - `fullscreen_dialog`：含“半屏/透明/浮层/沉浸式弹层”
   - `page`：明确“独立整屏页面/导航入口/深链页”
   - 否则 `inline`
5. 阶段 1 输出：
   - `SELECTED: image_id=... name=... size_dp=...`
   - `PRESENTATION: <value>（一句理由）`
   - `FILES: lib/.../<screen>.dart, assets/lanhu/<screen>/..., pubspec.yaml(asset snippet)`

## 阶段 2（审计 + 规格 + Dart + 资源）

前置：`selected_image_id` 已确定。

1. 调用 `lanhu_get_design_annotations(url, image_id)` 获取结构化标注（主路径）
2. 校验 `unit` 与关键字段（`layers/measurements`）
3. 调用 `lanhu_get_design_slices(url, image_id)` 获取切图与资源信息
4. 主路径生成规则：
   - 几何值按已归一的 Flutter `double` 输出
   - 文本值按已归一的 `fontSize` / `height` / `letterSpacing` 输出
   - 间距优先使用 measurements，缺项时回退几何关系
   - 圆角优先读取 `annotations.style.border_radius`
5. 若步骤 1~3 任一失败或缺关键字段，触发 `web_schema_fallback`
6. 输出 A) 审计区（必须完整）
7. 输出 B) 规格表（<=3 层组件树）
8. 输出 C) Dart Widget 文件内容（仅 Widget）
9. 输出 D) 资源清单（仅列表）

### B) 规格表字段（主路径）

- `component | widget | parent | strategy`
- `position(x,y) | size(w,h) | normalized_value`
- `font_size | line_height -> TextStyle.height | letter_spacing`
- `text_padding(measurements) | icon_text_distance | nearest_neighbor`
- `width_strategy | height_strategy | safe_area | scroll_strategy | large_screen_strategy | keyboard_strategy`
- `border_radius_source | border_radius_output`
- `asset_format(webp/png) | asset_output_dir(assets/lanhu/<screen>/) | asset`

### C) Dart Widget 内容约束

- 只允许输出 Dart Widget 文件内容
- 优先使用 `StatelessWidget`
- 需要根据页面风险显式体现 `SafeArea`、`LayoutBuilder`、滚动容器、键盘避让策略（SafeArea should NOT be used to replace design-specified spacing; only use SafeArea for areas not covered by the design）
- 资源引用使用：`Image.asset('assets/lanhu/<screen>/...')`
- 禁止输出未归一的 `*_raw`、schema 原值、XML 属性名
- 禁止输出 `pubspec.yaml` 全文、接入说明或验收说明

### D) 资源清单最少字段

- `asset_root=assets/lanhu/<screen>/`
- `pubspec_assets=assets/lanhu/<screen>/`
- `asset_format(webp/png) | asset_output_dir(assets/lanhu/<screen>/) | asset`

### 兜底路径补充字段（仅 fallback）

- `scale_formula=411/750`
- `conversion_rule=round(px * 411 / 750)`
- `schema_version_id`
- `schema_source_url`

除 A/B/C/D 外不要输出任何内容。
