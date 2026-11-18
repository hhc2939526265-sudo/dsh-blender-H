# Changelog

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 提交规范，版本号采用 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

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

[Unreleased]: https://github.com/hhc2939526265-sudo/dsh-blender-H/compare/v1.1.7...HEAD
[1.1.7]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.7
[1.1.6]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.6
[1.1.5]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.5
[1.1.4]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.4
[1.1.3]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.3
[1.1.2]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.2
[1.1.1]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.1
[1.1.0]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.0
[1.0.0]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.0.0
