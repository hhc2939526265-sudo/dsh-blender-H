# DSH Blender Bridge

> 原生 DSH 插件 × 独立 Blender Addon，基于本地 WebSocket 长连接的双向实时桥接，
> 打造「多模态输入 → AI 解析 → 3D 生产 → 迭代优化 → 渲染交付」全闭环工作流。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Blender](https://img.shields.io/badge/Blender-4.2%20LTS%20~%205.3-green.svg)](#)
[![Version](https://img.shields.io/badge/version-1.0.0-orange.svg)](CHANGELOG.md)

---

## 核心特性

- **双向实时桥接**：本地 WebSocket 长连接，30s 心跳检测、断线指数退避自动重连、连接状态实时可视化。
- **标准化协议**：6 字段 JSON 信封（指令 ID / 类型 / 参数体 / 状态 / 结果 / 错误），批量指令队列串行 / 并行执行。
- **多模态分片传输**：图片 / 视频断点续传 + MD5 校验，大文件稳定无损坏；成品图 / 视频反向回传预览。
- **图片驱动建模**：单 / 多图解析，三档面数精度，50+ 面部形状键、服装 / 发型分层、UV 展开、基础 PBR 烘焙、标准人形骨骼自动绑定。
- **视频驱动动画与特效**：21+ 关节轨迹复刻、帧率匹配降噪；粒子 / 辉光 / 流体 / 形变 / 镜头运动映射为可编辑节点。
- **自然语言建模**：中文提示词解析为 26 种建模指令、8 种动画指令、6 种材质指令。
- **材质渲染闭环**：PBR 节点树生成、批量材质管理、预设存取、Eevee / Cycles 切换、成品自动回传。
- **反向迭代**：模型 / 动画 / 材质 / 场景一键回传 DSH，支持多轮 AI 优化。
- **工程化与稳定性**：分级日志、指令校验、场景备份回滚、分批内存管理、闲置缓存释放、全链路异常兜底。

## 效果预览

> 截图占位：接入真实素材后替换 `assets/` 下图片。

| 角色建模 | 动捕复刻 | 特效还原 | 渲染回传 |
|---|---|---|---|
| ![](assets/preview_character.png) | ![](assets/preview_mocap.png) | ![](assets/preview_effect.png) | ![](assets/preview_render.png) |

## 仓库导航

```
dsh-blender-bridge/
├── src/
│   ├── dsh_plugin/            # DSH 插件前端（manifest / HTML / CSS / JS，无第三方依赖）
│   └── blender_addon/         # Blender Addon（Python，4.2 LTS ~ 5.3）
│       ├── core/              # 协议 / WebSocket 服务 / 分片传输 / 分发器 / 队列 / 桥接主控
│       ├── ai/                # AI 解析适配层（抽象 / Mock / HTTP / 注册降级）
│       ├── handlers/          # 建模 / 角色 / 动画 / 特效 / 材质 / 渲染 / 场景 / 导出 / 流水线
│       ├── compat/            # 版本兼容层
│       ├── config/            # 默认配置与运行时配置
│       ├── utils/             # 日志 / 备份 / 路径 / 内存清理
│       ├── operators.py       # 操作符与属性组
│       └── panel.py           # 侧边栏面板
├── docs/
│   ├── INSTALL.md             # 安装部署手册
│   ├── USAGE.md               # 使用说明书（18 条示例提示词）
│   ├── API.md                 # 通信协议 / 指令集 / 数据格式 / 扩展指南
│   └── ARCHITECTURE.md        # 架构设计文档
├── examples/
│   ├── case1_character_from_image/   # 单图角色 + 绑定全流程
│   ├── case2_mocap_effects/          # 行走动画 + 光效粒子复刻
│   └── case3_roundtrip_iteration/    # 回传二次迭代全流程
├── scripts/                   # 一键打包脚本（sh / ps1）
├── tests/                     # 协议 / 传输层单元测试（标准库）
├── assets/                    # 图标与预览资源
├── README.md / LICENSE / CHANGELOG.md / .gitignore
```

## 快速开始（三步）

```bash
git clone https://github.com/hhc2939526265-sudo/dsh-blender-H.git
```

1. **安装 Blender Addon**：Release 下载 `DSH_Blender_Bridge_Addon_v1.0.0.zip` →
   Blender 偏好设置 → 插件 → 从磁盘安装 → 勾选启用 → 侧边栏 `DSH Bridge` 启动服务。
2. **安装 DSH 插件**：Release 下载 `DSH_Blender_Bridge_Plugin_v1.0.0.zip` →
   DSH 插件管理本地安装 → 启用面板。
3. **连接使用**：两端地址端口保持一致（默认 `127.0.0.1:8765`）→ 点击连接 →
   上传图片 / 视频或输入提示词开始生产。

详细步骤见 [docs/INSTALL.md](docs/INSTALL.md)。

## 本地开发与打包

```bash
# 运行单元测试（无需 Blender）
python3 -m unittest discover -s tests -v

# 一键打包（Linux / macOS）
bash scripts/package_all.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts/package_all.ps1
```

产物输出到 `packages/`：Addon 安装包、DSH 插件包、完整源码包。

## 指令规模

- 建模指令 26 种｜动画指令 8 种｜材质指令 6 种｜特效指令 5 种
- 角色 / 渲染 / 场景 / 导出 / 流水线 / 自然语言指令若干，完整清单见 [docs/API.md](docs/API.md)

## FAQ

**Q：不接外部 AI 服务能用吗？**
A：可以。默认内置本地规则兜底（Mock），可离线跑通全流程演示；接入真实后端只需在配置中切换 `ai.provider`。

**Q：支持哪些 Blender 版本？**
A：4.2 LTS ~ 5.3，版本差异由 `compat/` 层隔离，低版本不支持的功能自动降级。

**Q：需要手动 pip 安装依赖吗？**
A：不需要。Blender 端仅用内置 Python 库与标准库；DSH 端无第三方前端依赖。

**Q：端口被占用怎么办？**
A：两端面板同步修改端口后重启 / 重连即可，范围 1024 ~ 65535。

更多排查见 [docs/INSTALL.md](docs/INSTALL.md#五常见环境问题排查)。

## 贡献指南

欢迎提交 Issue 与 Pull Request。提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：

- `feat:` 新功能　`fix:` 缺陷修复　`docs:` 文档　`refactor:` 重构
- `perf:` 性能　`test:` 测试　`chore:` 工程化

开发规范与扩展方式见 [docs/API.md](docs/API.md#六二次扩展开发) 与 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 开源协议

[MIT](LICENSE) © DSH-Blender Bridge Contributors
