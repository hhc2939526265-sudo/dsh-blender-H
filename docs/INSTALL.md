# 安装部署手册

> 适用版本：DSH Blender Bridge 1.0.0　｜　兼容 Blender 4.2 LTS ~ 5.3　｜　Windows / macOS / Linux

## 一、环境要求

| 项 | 要求 |
|---|---|
| Blender | 4.2 LTS 及以上，5.3 及以下（64 位） |
| DSH | 支持插件加载的桌面版本，内置 WebSocket 与文件读取能力 |
| Python | Blender 内置 Python 3.10+，**无需手动 pip 安装任何第三方依赖** |
| 网络 | 仅本机回环通信（127.0.0.1），不对外网暴露端口 |

## 二、Blender 端 Addon 安装

### 方式 A：安装预编译压缩包（推荐普通用户）

1. 在 Release 下载 `dsh_blender_bridge_addon.zip`（**不要解压**）。
2. 打开 Blender → 顶部菜单 `编辑(Edit) → 偏好设置(Preferences) → 插件(Add-ons)`。
3. 点击右上角 `从磁盘安装(Install from Disk...)`，选择该 zip 包。
4. 勾选启用 `3D View: DSH Blender Bridge`。
5. 在 3D 视图侧边栏（按 `N` 调出）找到 `DSH Bridge` 标签页。

### 方式 B：从源码目录安装

1. 进入 `src/blender_addon/` 目录。
2. 将该目录重新打包为 zip（保持 `__init__.py` 在压缩包根层级），或直接在偏好设置中指向源码目录开发调试。
3. 启用方式同方式 A。

### 验证安装

- 侧边栏出现 `DSH Bridge` 面板；
- 点击 `启动桥接服务`，状态指示灯变为绿色「运行中」；
- 日志输出 `WebSocket 服务已启动 ws://127.0.0.1:8765`。

## 三、DSH 端插件安装

1. 在 Release 下载 `dsh_plugin.zip`。
2. 打开 DSH → 插件管理 → 安装本地插件，选择该 zip 包。
3. 启用 `DSH Blender 双向桥接`，面板自动加载。
4. 面板顶栏确认地址 `127.0.0.1`、端口 `8765` 与 Blender 端一致，点击 `连接`。

> 插件配置项（精度、帧率、采样、日志级别等）在面板内修改后自动持久化，
> 也可在 `manifest.json` 的 `config` 段调整默认值。

## 四、通信配置教程

### 4.1 端口配置

- Blender 端：面板 `端口` 输入框修改 → 点击 `重启桥接服务`。
- DSH 端：顶栏端口同步修改 → 点击 `连接`。
- 两端端口必须一致；默认 `8765`。若被占用，可改为 `1024 ~ 65535` 之间任意未占用端口。

### 4.2 Blender 可执行文件路径

- DSH 端顶栏 `Blender` 输入框旁点击 `扫描`，插件按当前平台列出常见安装候选路径（Windows：`C:/Program Files/Blender Foundation/Blender X.X/blender.exe`；macOS：`/Applications/Blender.app/Contents/MacOS/Blender`；Linux：`/usr/bin/blender`、`/opt/blender/blender`）；
- 未扫描到或路径不符时，可在输入框手动填写 `blender.exe` / `Blender` 可执行文件完整路径；
- 该路径用于后续由 DSH 拉起 Blender 进程；仅使用已手动打开的 Blender 实例时可留空。

### 4.3 心跳与重连

- 心跳间隔默认 30 秒，超时 10 秒未收到 Pong 主动断开；
- DSH 端开启 `断线自动重连` 后，按 1s → 2s → 4s … 上限 30s 指数退避重连；
- 重连后文件传输自动走断点续传，仅补发缺失分片。

### 4.4 外部 AI 推理服务（可选）

默认使用本地规则兜底（Mock），可离线演示全流程。接入真实后端时：

1. 编辑 Blender Addon 配置目录下 `config/runtime_config.json`：

```json
{
  "ai": {
    "provider": "http",
    "endpoint": "http://127.0.0.1:9000/ai",
    "timeout": 15,
    "api_key": ""
  }
}
```

2. 推理网关按《开发接口文档》「外部 AI 服务对接」一节实现 `analyze_character /
   analyze_motion / analyze_effect / parse_nl` 四个方法；
3. 远端不可用时插件自动降级 Mock，不会中断工作流。

## 五、常见环境问题排查

| 现象 | 可能原因 | 处理方式 |
|---|---|---|
| 点击启动服务提示端口绑定失败 | 端口被占用 / 权限不足 | 更换端口；Windows 检查是否有其他程序占用 8765 |
| DSH 面板一直「未连接」 | Blender 服务未启动 / 端口不一致 / 防火墙拦截 | 先确认 Blender 面板服务运行中；核对两端端口；本机回环无需放行防火墙 |
| 连接后握手无指令清单 | 版本不兼容 / Addon 未完整加载 | 重启 Blender；检查 Blender 版本是否在 4.2 ~ 5.3 区间 |
| 图片 / 视频传输校验失败 | 分片丢失 / 文件被占用 | 查看日志 MD5 期望值与实际值；关闭占用文件的程序后重传 |
| 建模 / 绑定后权重异常 | 场景存在非标准网格 | 先执行 `mesh.recalc_normals` 与 `mesh.origin_set`，再重新绑定 |
| Cycles 采样项不生效 | 当前引擎为 Eevee | 在材质渲染页切换引擎后再设置采样 |
| 插件加载报 `ModuleNotFoundError` | 打包层级错误 | 确认 zip 根目录直接包含 `__init__.py`，不要多套一层文件夹 |

## 六、目录与产物位置

| 数据 | 默认位置 |
|---|---|
| 接收的图片 / 视频分片 | 用户目录 `DSH_Bridge/transfer_cache/` |
| 渲染成品 | 用户目录 `DSH_Bridge/render_output/` |
| 场景备份 | 用户目录 `DSH_Bridge/backups/` |
| 材质预设 | 用户目录 `DSH_Bridge/presets/` |
| 运行日志 | 用户目录 `DSH_Bridge/logs/` |
| 运行时配置 | Addon 目录 `config/runtime_config.json` |

> Windows 用户目录：`%APPDATA%/DSH_Bridge`；macOS：`~/Library/Application Support/DSH_Bridge`；
> Linux：`~/.dsh_bridge`。可用环境变量 `DSH_BRIDGE_HOME` 覆盖根目录。
