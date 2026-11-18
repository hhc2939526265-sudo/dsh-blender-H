# Changelog

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 提交规范，版本号采用 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

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

[Unreleased]: https://github.com/hhc2939526265-sudo/dsh-blender-H/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.1
[1.1.0]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.0
[1.0.0]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.0.0
