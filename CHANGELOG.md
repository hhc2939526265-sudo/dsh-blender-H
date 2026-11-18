# Changelog

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 提交规范，版本号采用 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

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

[Unreleased]: https://github.com/hhc2939526265-sudo/dsh-blender-H/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.1.0
[1.0.0]: https://github.com/hhc2939526265-sudo/dsh-blender-H/releases/tag/v1.0.0
