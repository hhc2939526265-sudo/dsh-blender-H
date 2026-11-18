# Changelog

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 提交规范，版本号采用 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- 预留：后续版本迭代记录位。

## [1.0.0] - 2026-11-18

### Added
- 通信层：基于本地 WebSocket 长连接的 DSH ↔ Blender 双向桥接，支持 30s 心跳检测、断线自动重连、连接状态实时可视化。
- 协议层：标准化 JSON 通信协议（指令 ID / 指令类型 / 参数体 / 执行状态 / 返回结果 / 错误信息），支持批量指令队列串行 / 并行执行。
- 传输层：图片、视频分片传输，断点续传 + MD5 校验，大文件稳定无损坏。
- Blender 端：可独立安装的 Addon，后台服务线程化运行，不阻塞主界面；兼容 Blender 3.6 LTS ~ 4.3。
- 图片驱动建模：单 / 多图上传解析，三档面数精度，基础形状键、服装分层、发型面片、原点归位、法线统一、UV 展开、基础 PBR 烘焙、标准人形骨骼与权重分配。
- 视频驱动动画与特效：21+ 关节轨迹复刻，粒子 / 辉光 / 流体 / 形变 / 镜头运动映射，帧率匹配与时序对齐。
- 自然语言建模：25+ 建模指令集，参数化批量生成，场景自动备份与一键回滚。
- 动画模块：关键帧位移 / 旋转 / 缩放，骨骼绑定与走跑跳循环，刚体 / 柔体 / 布料 / 流体物理，路径约束。
- 材质渲染：PBR 节点树生成，Eevee / Cycles 切换，批量材质管理，渲染结果自动回传。
- DSH 面板：上传拖拽、提示词输入、预览窗口、执行 / 暂停 / 停止、参数配置、历史预设、分级日志。
- 稳定性：全链路异常捕获、四级日志、指令校验、分批内存管理、闲置缓存释放。
- 工程化：完整文档（安装手册 / 使用说明书 / 接口文档）、3 个演示案例、一键打包脚本、README / LICENSE / .gitignore。

[Unreleased]: https://github.com/your-org/dsh-blender-bridge/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/your-org/dsh-blender-bridge/releases/tag/v1.0.0
