# Changelog

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 提交规范，版本号采用 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [1.1.9] - 2026-11-19

### Fixed
- **P1 对象失效 RNA**：`require_object` / `list_objects` 解析后复核 RNA 可读，失效句柄抛明确参数错误；`mesh.join` 执行前二次剔除已失效成员，避免 `StructRNA of type Object has been removed`。
- **P2 曲线 / 类型错配**：挤出 / 环切 / 内插面 / 法线 / 焊接 / UV / 分离 / 布尔等网格指令执行前校验 `MESH` 类型；`mesh.join` 自动跳过曲线 / 骨架 / 灯光 / 相机并在回执列出；新增 `mesh.convert` 将曲线 / 文字 / 元球 / 曲面转为网格。
- **P3 连接竞态**：前端连接代际号隔离新旧 WebSocket，旧实例回调不再触发重连；新建连接前先拆除残留连接与定时器，消除一轮一建断与多连接并存；握手阶段 `10054` 归为网络层告警。
- **重复触发制作**：前端各类制作动作增加并发锁，上一轮未结束再次触发直接忽略；`boot()` 只初始化一次，避免宿主重复回调导致事件重复绑定、一次操作被执行多次。
- **动画关键帧校验**：关键帧数值分量数与位置 / 旋转 / 缩放严格对齐，分量不符提前抛参数错误。

### Changed
- **建模还原度**：角色装配消费 AI 规格的肩宽 / 髋宽 / 躯干长 / 腿长 / 脸型 / 发型参数；皮肤 / 上衣 / 头发按图片分区取色；Mock 兜底按图片路径确定性生成差异化体型；整体平滑着色。
- 指令总数 113 → 114（新增 `mesh.convert`）；单元测试 78 个全部通过。

### 保留项
- 高精度人体重建仍依赖外部推理后端（`ai.provider=http`）；本地 Mock 仅生成拓扑规范、可二次编辑的占位资产。
- 真机 Blender 4.2 LTS ~ 5.2 算子 / 解算行为未逐一回归，5.3.0 已真机验证主链路。

## [1.1.8] - 2026-11-19

> 本轮在 Blender **5.3.0** 真机上完成审计、修复与回归，完整证据与复现脚本见 [AUDIT.md](AUDIT.md)。

### Fixed

- **A1（致命）** `addon_state.py` 模块内 `def get_logger()` 遮蔽 `from .utils.logger import get_logger` 导入，`get_logger("dsh_bridge", level=...)` 抛 `TypeError: get_logger() got an unexpected keyword argument 'level'`，插件注册直接失败。改为导入别名 `make_logger`。
- **A2（致命）** `__init__.py` 在 `register()` 阶段遍历 `bpy.data.scenes`，而注册期 `bpy.data` 仍是 `_RestrictData` → `AttributeError: '_RestrictData' object has no attribute 'scenes'`。改为 `_sync_panels()` 守卫 + `bpy.app.timers.register(..., first_interval=0.2)` 延迟同步。
- **V1** 闲置 TCP 连接可永久占满桥接（本地 DoS）：accept 后设 `handshake_timeout`（默认 5s），未握手连接数超 `max_connections*4` 直接 `503`，已握手连接才计入并发。
- **V2** 并发上限 off-by-one：`max_connections=3` 时第 3 条被拒 → 改为只统计已握手连接，配置值即实际可用数。
- **V4** 不校验客户端帧掩码：未掩码帧按 RFC 6455 回 close `1002`。
- **V5** 单帧 / 分片无上限：新增 `max_message_size_mb`（默认 8），超限回 `1009`（控制帧另校验 FIN 与 125 字节上限）。
- **V6** `400` 响应状态行写死 `Forbidden`：改为状态码短语表（`400 Bad Request` / `403 Forbidden` / `503 Service Unavailable`）。
- **V7** 心跳 PING 每秒重复：增加 `last_ping_sent` 去重，未握手连接不参与心跳。
- **V8** 口令非常量时间比较：改 `hmac.compare_digest`。
- **V9** 配置写死在插件安装目录（升级即丢）：迁到 `%APPDATA%\DSH_Bridge\config\runtime_config.json`，旧文件首次加载自动迁移，`os.replace` 原子写。
- **V10** 传输层：`verify_md5` 开启时空 md5 会跳过校验 → 必填；resume 仅在 `total_size/chunk_count/md5` 一致时生效；`add_chunk` 先校验索引再 `base64.b64decode(validate=True)`；`finish` 缺 md5 合并前拒绝落盘。
- **V11** 指令队列无上限、丢弃不回包：新增 `QueueFullError` → `E_BUSY`（默认上限 256，可配 `max_pending_commands`），排队超时被丢弃的指令补发 `E_TIMEOUT`。
- **V12** handler 参数校验缺失，错误类型 payload 会让 Blender C API 抛 `SystemError: <built-in method get of bpy_prop_collection ...>`：新增 `utils/errors.py`（`ParamError` + `require_*`/`get_*` 中文提示），`dispatcher` 统一归 `E_PARAM`。
- **V13** DSH 桌面应用 Origin 为 `dsh-app://app`，上游只认 `localhost/127.0.0.1/::1` → 状态胶囊每 5 秒被 403，指示灯永远离线：`_check_origin` 支持完整 Origin 比较，默认 `allowed_origins` 放行 `dsh-app://app`，并引入 `CONFIG_VERSION = 2` 自动迁移旧配置；`bridge.py` 在配置为空时回落到默认值。

### Changed

- 版本号 `1.1.7` → `1.1.8`。
- 配置项新增 `handshake_timeout`、`max_message_size_mb`、`max_pending_commands`；`allowed_origins` 支持完整 Origin 字符串。
- 新增 `src/dsh_bundle/`：可被 DSH 插件管理器直接安装的原生 bundle（`package.json` + `cordis.patch.yml` + `blender_status` / `blender_commands` / `blender_exec` 三个工具 + 输入框状态胶囊）。原 `src/dsh_plugin/` 的自创 `manifest.json` 格式与虚构 `window.DSH` 宿主 API 无法加载，保留作历史参考并标注弃用。

### 测试

- 新增 `utils/errors.py` 级别参数校验后，113 条指令空 payload：**28 成功 / 85 失败 / 0 `E_EXEC` / 0 崩溃**（修复前 25 / 88 / 1）。
- 错误类型 payload fuzz 两轮 226 条：**0 `E_EXEC`**（修复前约 70 条 `SystemError`）。
- 协议用例 7/7、传输用例 10/10、纯 Python 回归 39/39（含连接上限、握手超时回收、未掩码 1002、超限 1009、口令、Origin 迁移）。
- 真实工作流冒烟 13 成功（建模 / 变换 / 倒角 / PBR / 粒子 / 备份 / 渲染 / GLB 导出 / 算子调用）/ 7 条预期失败。
- 端到端：`blender_status` → `running:true, addon_version:1.1.8, command_count:113`。
- 说明：上游 `tests/` 中桩化断言基于旧的 `E_EXEC` 文案，未纳入本轮回归，欢迎按 `E_PARAM` 语义同步。

## [1.1.7] - 2026-11-18

### Fixed
- **N1**：插件启停新增模块名前缀白名单 `addon_module_allowlist`，`addon.enable` / `addon.disable` 执行前校验；文档同步说明。
- **N2**：`addon.nodegroup_apply` 覆写输入前按套接字类型做基础转换（INT / FLOAT / BOOLEAN / STRING / VECTOR / COLOR），类型不兼容在执行前抛错。
- **N3**：注册表测试新增目录推荐指令交叉断言，catalog 内全部 `bridge_commands.cmd` 必须已注册，防止推荐到失效指令。
- **N4**：`transfer.begin` 拒绝 `total_size <= 0` 的零字节会话；累计字节校验不再跳过 0 大小分支。
- **N5**：`transfer.py` 顶部统一 `import time`，移除 `__import__("time")` 与函数内局部导入。
- **N6**：前端预设卡片名称 / 描述统一经 `_esc` 转义后再插入 innerHTML。

### 测试
- 新增零大小会话拒绝、模块白名单拒绝、节点输入类型转换 / 不兼容用例；目录指令与注册表交叉断言纳入注册测试。共 74 个单元测试全部通过。

## [1.1.6] - 2026-11-18

### Added
- 内置 20 个常用第三方插件目录映射（MPFB2、Jiggle Physics、BagaPie、Sword Trail、Extra Nodes、Simply Cloth、Alt Tab Easy Fog2、Auto-Rig Pro、Faceit、Simply Cloth Studio 2、Hair Pro、Animcraft、Geo-Scatter、RockForms、True Terrain、NeXus、VFX Toolkit、Style Engine、Baker Wrangler、Light Painter），每条目给出能力分类、工作流与推荐桥接指令。
- 新增 `addon.catalog` 指令：按能力 / 关键词检索目录；`addon.match` 回执补充 `catalog_hits`，已启用列表未命中时返回目录最贴合条目。
- Mock 自然语言规则补充布料物理 / 软体 / 地形 / 散布 / 烘焙 / 绑定 / 表情 / 岩石 / 风格化关键词映射。

### 测试
- 新增目录条目完整性、分类 / 关键词检索与意图匹配用例；共 70 个单元测试全部通过。

## [1.1.5] - 2026-11-18

### Added
- 插件生态新增 6 条指令（4 → 10）：`addon.enable` / `addon.disable` 运行时启停、`addon.status` 生态自检与策略回执、`addon.operator_search` 全局算子检索、`addon.operator_batch` 批量算子套用（单对象失败隔离）、`addon.nodegroup_apply` 几何节点组挂载与输入覆写。
- 新增配置开关 `allow_addon_enable` / `allow_addon_disable`；模块名格式校验，禁止桥接自身被启停；算子安全策略抽取为统一校验函数，调用与批量套用共用。

### Changed
- API 文档、使用说明与安装配置表同步补充新指令参数、示例与开关说明；示例提示词增至 38 条。

### 测试
- 新增启停 / 检索 / 批量 / 节点组守卫与注册清单用例，共 65 个单元测试全部通过。

## [1.1.4] - 2026-11-18

### Added
- 动画新增 4 条（战斗姿态 / 装配）：`anim.bone_keyframe` 单骨骼关键帧、`anim.pose` 批量骨骼姿态、`anim.follow_target` 目标跟随约束、`anim.action_mix` 动作层混合规格。
- 特效新增 8 条（仙侠能量 / 场景氛围）：`effect.trail` 剑气拖尾、`effect.shockwave` 环形冲击波、`effect.shield` 能量护盾、`effect.lightning` 雷弧闪电、`effect.aura` 灵气光环、`effect.debris` 碎石碎片、`effect.spark` 火花迸发、`effect.camera_shake` 镜头震动。
- 材质新增 1 条：`material.emission` 自发光能量材质。
- 新增案例 4「仙侠打斗镜头」演示指令序列；Mock 自然语言规则补充剑气 / 护盾 / 雷弧 / 灵气 / 冲击波 / 火花 / 碎片 / 震屏关键词；前端新增 5 个特效模板。

### Changed
- 指令规模更新为建模 35 / 动画 17 / 材质 10 / 特效 18；API 文档、示例提示词与案例清单同步。

### 测试
- 新增打斗姿态 / 约束 / 特效时序守卫与注册清单用例，共 58 个单元测试全部通过。

## [1.1.3] - 2026-11-18

### Added
- 建模新增 9 条（人物形体 / 场景道具）：`mesh.duplicate`、`mesh.join`、`mesh.separate`、`mesh.screw`、`mesh.wireframe`、`mesh.displace`、`mesh.edge_split`、`mesh.shrinkwrap`、`mesh.crease`。
- 动画新增 5 条（角色绑定 / 装配）：`anim.clear`、`anim.ik`、`anim.copy_transform`、`anim.action_list`、`anim.parent_set`。
- 材质新增 3 条：`material.assign`、`material.clear`、`material.list`。
- 特效新增 5 条（场景氛围 / 角色特效）：`effect.force_field`、`effect.light`、`effect.world`、`effect.hair`、`effect.motion_blur`。
- Mock 自然语言规则补充复制 / 合并 / 线框 / 置换 / 毛发 / 灯光 / 风场关键词映射；案例 2 演示灯光、风场与运动模糊。

### Changed
- 指令规模更新为建模 35 / 动画 13 / 材质 9 / 特效 10；API 文档与示例提示词同步更新。

### 测试
- 新增注册清单与参数守卫用例，共 52 个单元测试全部通过。

## [1.1.2] - 2026-11-18

### Fixed
- 分片会话新增累计接收字节统计：单分片大小超过分片上限、或累计字节超出登记 `total_size` 时拒绝并清理脏会话，回执附带 `received_bytes`。
- 前端历史条目的指令名与状态标签统一经 HTML 转义后再写入页面，避免潜在注入。

### Changed
- `command_timeout` 落地为**排队等待超时**：条目在队列中等待超时即被丢弃并计入 dropped；文档明确标注 Blender 主线程不可抢占，正在执行的指令无法中途中断，执行超时需待后台线程模型就绪后实现。
- 文档补充算子前缀白名单的生产部署建议；测试新增排队超时与传输字节边界用例（46 个用例全部通过）。

## [1.1.1] - 2026-11-18

### Fixed
- 修复角色建模处理器误调用不存在的 `version_compat.deselect_all()`，改为公共辅助模块 `H.deselect_all()`，真机 Blender 内合并 / 绑定流程不再抛 AttributeError。
- 自然语言解析产出的 `"active"` 对象引用无法按名解析导致 KeyError；`active`（含空值）现统一解析为当前活动对象并做非空校验。
- 修复 `character.rig_object` 父子关系判断误用对象名集合比较 `children` 的问题；材质烘焙改为按节点类型 `BSDF_PRINCIPLED` 查找，节点被重命名后不再取空。
- 补齐建模曲线 / 路径约束坐标点数量与分量校验、关键帧数值长度校验、循环动画类型校验、形变时序帧号校验，非法参数在执行前拦截。
- 备份槽位重启后按目录扫描回补历史记录；回滚槽位越界返回明确错误，不再抛 IndexError。
- 前端历史记录失败回执不再误记为 SUCCESS；预览文件名做 HTML 转义；下行重组后先做分片完整性与 MD5 校验再生成预览。

### Security
- WebSocket 握手增加 Origin 白名单校验（本地回环默认放行）、可选共享口令校验与并发连接数上限，缓解浏览器跨站 WebSocket 劫持（CSWSH）。
- 第三方插件算子调用增加前缀白名单与危险算子黑名单（工程 / 脚本 / 控制台等），参数类型白名单保留。
- 场景导入默认限定在传输 / 临时目录；场景导出、材质预设文件名经 `basename` 清洗；渲染输出目录与材质贴图路径收敛到允许目录内，防目录穿越与任意路径读写。
- 分片传输增加分片索引范围校验、单文件大小上限与索引集合完整性比对。

### Changed
- 运行期目录（传输缓存 / 渲染输出 / 日志）统一收敛到用户目录 `DSH_Bridge/`，不再写入 Addon 安装目录；日志保留天数接入配置项。
- 接通 `system.shutdown` 指令（回执后延迟停止服务）；`transfer.ack` / `system.pong` / `render.result_back` 标注为预留指令。

## [1.1.0] - 2026-11-18

### Added
- 第三方插件生态：新增 `addon.list / addon.detail / addon.invoke / addon.match` 四条指令。
- 枚举 Blender 会话中已启用的第三方 Addon，读取 `bl_info` 元信息（名称 / 作者 / 版本 / 类别 / 描述），按关键词归类到建模 / 绑定 / 动画 / 特效 / 材质 / 渲染 / 资产 / 导入导出。
- 算子发现：递归遍历已注册 Operator，按 ID 前缀归属插件，提取算子标签与参数定义（标识符 / 类型 / 是否必填）。
- 通用安全调用入口：算子存在性校验、参数类型白名单过滤、直接执行 / 交互面板两种模式，异常收敛为回执；`allow_addon_invoke` 总开关。
- 自然语言意图匹配：按关键词命中度为插件打分，返回最贴合插件及其可用算子。
- DSH 面板新增「插件生态」页签：插件列表、详情与算子列表、意图匹配、算子调用表单与结果回执。

## [1.0.0] - 2026-11-18

### Added
- 通信层：基于本地 WebSocket 长连接的 DSH ↔ Blender 双向桥接，支持 30s 心跳检测、断线自动重连、连接状态实时可视化。
- 协议层：标准化 JSON 通信协议（指令 ID / 指令类型 / 参数体 / 执行状态 / 返回结果 / 错误信息），支持批量指令队列串行 / 并行执行。
- 传输层：图片、视频分片传输，断点续传 + MD5 校验，大文件稳定无损坏。
- Blender 端：可独立安装的 Addon，后台服务线程化运行，不阻塞主界面；兼容 Blender 4.2 LTS ~ 5.3。
- 图片驱动建模：单 / 多图上传解析，三档面数精度，基础形状键、服装分层、发型面片、原点归位、法线统一、UV 展开、基础 PBR 烘焙、标准人形骨骼与权重分配。
- 视频驱动动画与特效：21+ 关节轨迹复刻，粒子 / 辉光 / 流体 / 形变 / 镜头运动映射，帧率匹配与时序对齐。
- 自然语言建模：25+ 建模指令集，参数化批量生成，场景自动备份与一键回滚。
- 动画模块：关键帧位移 / 旋转 / 缩放，骨骼绑定与走跑跳循环，刚体 / 柔体 / 布料 / 流体物理，路径约束。
- 材质渲染：PBR 节点树生成，Eevee / Cycles 切换，批量材质管理，渲染结果自动回传。
- DSH 面板：上传拖拽、提示词输入、预览窗口、执行 / 暂停 / 停止、参数配置、历史预设、分级日志。
- 稳定性：全链路异常捕获、四级日志、指令校验、分批内存管理、闲置缓存释放。
- 工程化：完整文档（安装手册 / 使用说明书 / 接口文档）、3 个演示案例、一键打包脚本、README / LICENSE / .gitignore。

[Unreleased]: https://github.com/hhc2939526265-sudo/dsh-blender-H/compare/v1.1.9...HEAD
[1.1.9]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.9
[1.1.8]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.8
[1.1.7]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.7
[1.1.6]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.6
[1.1.5]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.5
[1.1.4]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.4
[1.1.3]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.3
[1.1.2]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.2
[1.1.1]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.1
[1.1.0]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.0
[1.0.0]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.0.0
