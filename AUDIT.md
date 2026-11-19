# DSH Blender Bridge 插件审计报告（v1.1.8 复核版）

审计对象：`https://github.com/hhc2939526265-sudo/dsh-blender-H`（上游 v1.1.7，MIT）
审计 / 修复日期：2026-11-19
环境：Windows 11 + Blender **5.3.0**（便携版 `G:\blender1\blender.exe`，build 2026-11-10）+ Python 3.11
审计基线：官方 zip 解压到 `_dsh-blender\addon-orig\`，逐文件哈希确认除下述修复外与上游逐字节一致，故结论代表上游代码。

安装位置（已装并用 GUI 实测通过）：
`%APPDATA%\Blender Foundation\Blender\5.3\scripts\addons\dsh_blender_bridge`
可安装包：`_dsh-blender\DSH_Blender_Bridge_Addon_v1.1.8-fixed.zip`（102,718 B，根目录 `dsh_blender_bridge/`）

---

## 1. 结论

| 问题 | 结论 |
|---|---|
| 能运行吗？ | **能**。上游原包在 Blender 5.x 上装不上（2 个致命 bug，已修）；修好后 113 条指令可调，建模 / 材质 / 特效 / 备份 / 渲染 / 导出实测跑通，DSH 状态指示灯也已连通。 |
| 有漏洞吗？ | 没有 RCE 面（无 `eval`/`exec`/`subprocess`/`pickle`）。原有 12 项问题中 **11 项已修**，剩 1 项属于设计取舍（本机任意 `localhost` 页面可驱动 Blender，默认无口令）。 |
| 有错误代码吗？ | 修复前 fuzz 时约 70/113 条会抛 Blender C API 的 `SystemError`；现在 **0 条 E_EXEC、0 崩溃**，参数错误统一为 `E_PARAM`（中文提示）。 |
| 谁适合用？ | 本机单人使用：开箱可用。多人 / 不受信环境：建议设 `auth_token`（见第 6 节）。 |

---

## 2. 已修复（上游 2 个致命 bug + 12 项审计问题）

### A1. 日志模块名字遮蔽（致命，插件无法注册）

`addon-src\addon_state.py:17`
`from .utils.logger import get_logger as make_logger` —— 原来 `from .utils.logger import get_logger`，
而文件第 49 行自己又定义了 `def get_logger()`，模块级定义覆盖导入，导致 `:35`
`logger = make_logger(...)` 的 `level=` 参数报 `TypeError: get_logger() got an unexpected keyword argument 'level'`。

### A2. `register()` 期间访问 `bpy.data`（致命，启用即崩）

`addon-src\__init__.py:48-62` —— `register()` 里 `bpy.data` 仍是 `_RestrictData`，
`for scene in bpy.data.scenes` 抛 `AttributeError: '_RestrictData' object has no attribute 'scenes'`。
改为本地 `_sync_panels()` 闭包：`hasattr(scene, "dsh_bridge")` 守卫 + `bpy.app.timers.register(_sync_panels, first_interval=0.2)` 延迟一次。

### V1. 闲置连接可永久占满桥接（中危，本地 DoS）

`core\ws_server.py:164` accept 后立即 `client.settimeout(self._handshake_timeout)`；
`:169-172` 未握手连接数超过 `max_connections*4` 直接 `503 连接过多，请稍后重试`；
`:258` 并发只统计已握手连接 `active >= self._max_connections`。
实测：4 条只连不握手的裸 socket 全部在 2s 内被关闭，期间合法客户端仍能 101 接入。

### V2. 并发上限 off-by-one

`core\ws_server.py:258` 改为只统计 `handshaked` 连接。实测 `max_connections=3`：3 条成功、第 4 条 `403 连接数已达上限`。

### V3. 本机任意网页可驱动 Blender（**保留**，设计取舍）

`core\ws_server.py:206` 仍放行 `localhost / 127.0.0.1 / ::1` 任意端口且默认 `auth_token=""`。
这是「浏览器 UI 直连本机桥接」的固有代价；外站 Origin（`http://evil.example`）、`Origin: null`、`file://` 均被 403。
**缓解办法：设 `auth_token`**（Blender 面板 → 连接设置；DSH 侧 bundle config 配同一个 `token`）。

### V4. 未校验客户端掩码

`core\ws_server.py:386` 未掩码帧 → `WebSocketError`，`:487 _send_close` 回 `1002`。实测收到 `opcode=8 code=1002`。

### V5. 帧 / 分片无上限

`core\ws_server.py:397` 单帧超 `max_message_bytes` → `1009`；`:447` 分片累计超限 → `1009`。实测 3000B 帧（上限 2048）收到 `1009`。

### V6. 400 状态行写死 Forbidden

`core\ws_server.py:307 _reject_raw` 用短语表 `{400: Bad Request, 403: Forbidden, 503: Service Unavailable}`。实测缺 `Sec-WebSocket-Key` → `HTTP/1.1 400 Bad Request`。

### V7. 心跳 PING 每秒重复

`core\ws_server.py:536-539` 增加 `now - last_ping_sent >= heartbeat_interval` 条件并记录发送时间；未握手连接跳过心跳。

### V8. 口令非常量时间比较

`core\ws_server.py:228 _check_token` 改用 `hmac.compare_digest`。

### V9. 配置写在插件安装目录（升级即丢）

`config\default_config.py:24-27`：`CONFIG_DIR = %APPDATA%\DSH_Bridge\config`，
`LEGACY_CONFIG_PATH` 指向旧位置，加载时自动迁移一次并原子落盘（`.tmp` + `os.replace`）。

### V10. 传输层三处语义缺陷

`core\transfer.py`：
- `:143` `verify_md5` 开启时 `begin` 必须带 md5，否则拒绝；
- `:154` 续传仅当 `total_size / chunk_count / md5` 与会话一致，否则丢弃旧会话重建（同 id 换文件不再错乱）；
- `:191` `add_chunk` 先校验 file_id/index/data 类型与索引范围，再 `base64.b64decode(..., validate=True)`，失败回「data 不是合法的 base64 编码」；
- `:220` `finish` 在 md5 缺失时**合并前**拒绝落盘。

### V11. 队列无上限 + 丢弃不回包

`core\queue.py:23,52-57` 新增 `QueueFullError`（上限 `max_pending`，默认 256，可配 `max_pending_commands`）；
`core\bridge.py:213` 队满回 `E_BUSY`；`bridge.py:226-230` 排队超时被丢弃的指令补发 `E_TIMEOUT`。

### V12 / 错误代码：handler 参数校验统一

新增 `utils\errors.py`：`ParamError(ValueError)` + `require_* / as_* / get_*` 系列（类型不符抛中文提示，如「location 需为 3 个分量的数组，收到 2 个」）。
`core\dispatcher.py:100-104` 在 `KeyError` 之前捕获 `ParamError` → `E_PARAM`（原来一律 `E_EXEC`）。
10 个 handler 文件全部扫过；`handlers\addons.py:238` 显式拦截 `None`（`bpy_prop_collection.get(None)` 会抛 C API 的 `SystemError`）。

### V13.（本轮新发现）DSH 桌面应用 Origin 被拒 → 指示灯永远离线

DSH 客户端页面 Origin 是 **`dsh-app://app`**，上游 `_check_origin` 只认 hostname `localhost/127.0.0.1/::1`，
于是状态胶囊每 5s 重连一次、每次被 403 `Origin 不在白名单`，而命令行侧（Node 无 Origin 头）却一切正常，极易误判成「插件没启动」。

- `core\ws_server.py:206` 白名单支持完整 Origin（`scheme://host`），hostname 匹配保持兼容；
- `config\default_config.py:58` 默认 `allowed_origins = ["dsh-app://app"]`；
- `config\default_config.py:33,130-148` 引入 `CONFIG_VERSION = 2` 与 `_migrate`，旧配置（无版本号）自动补上该 Origin；
- `core\bridge.py:114-116` 再兜一层：配置里 `allowed_origins` 为空时回落到默认值（老版本写下的 `[]` 不会让指示灯永久离线）。

---

## 3. 回归验证（全部实测，非推断）

| 项目 | 修复前 | 修复后 |
|---|---|---|
| 113 指令 · 空 payload | 25 SUCCESS / 88 FAILED，`effect.lightning` E_EXEC | **28 SUCCESS / 85 FAILED / 0 E_EXEC / 0 崩溃** |
| 113 指令 · 错误类型 payload（fuzz，两轮 226 条） | ~70 条 `SystemError`（`bpy_prop_collection.get`） | **每轮 28 SUCCESS / 85 FAILED / 0 E_EXEC / 0 崩溃** |
| 协议层（7 例：缺字段 / 空 cmd_id / payload 非对象 / status 非法…） | 7/7 | **7/7**，错误码与文案不变 |
| 传输层（10 例：穿越 / 超限 / md5 / 续传 / base64 / 越界） | 穿越已拦、其余 3 处缺陷 | **10/10 符合新语义**（`../../evil.txt` 仍落 `save_dir\evil.txt`） |
| 真实工作流冒烟 | — | **13 SUCCESS**（cube / transform / bevel / PBR / 粒子 / 备份 / 渲染 / GLB 导出 / 算子调用），7 条**预期失败**（`uv_sphere` 非法、`mesh.boolean` 缺 `operand`、`anim.keyframe` 缺 `frames`、黑名单算子、`system.stop` 未注册） |
| 纯 Python 单元 / 黑盒回归 | — | **39/39 PASS**（传输 13 + 队列 5 + WS 17 + 配置迁移 4） |
| WS 黑盒（口令 / Origin / Bearer / 并发 / 掩码 / 超限 / 回收） | 未掩码帧被回显、第 3 条被拒、`400 Forbidden` | 未掩码 → `1002`、超限 → `1009`、3 条成功第 4 条 403、闲置连接回收后可正常接入、`400 Bad Request` |
| DSH 端到端（GUI Blender + 原生 bundle） | 指示灯离线（Origin 403） | `blender_status` → `running:true, addon_version:1.1.8, command_count:113, connections:2`（指示灯 + 工具各一条）；`blender_exec mesh.add_primitive{monkey}` → `DSH_FinalCheck` 507 顶点 |

复现脚本：`_dsh-blender\{audit_dynamic.py, audit_ws_server.py, audit_ws_client.py, test_core_hardening.py, serve_gui.py, live_check.mjs}`；
报告：`audit_report.jsonl`、`audit_report_empty.jsonl`、`audit_report_before_fix.jsonl`。

---

## 4. 仍然存在的风险 / 设计取舍

1. **默认无口令**（V3）：本机任意 `localhost` 页面仍可驱动 Blender。建议生产前设 `auth_token`。
2. **空 payload 宽容**：`render.execute`、`scene.backup/rollback`、`export.*`、`character.build` 等 28 条指令在空参数下仍会真的执行（有副作用）。这是上游「参数全部可选」的设计，未强改为必填以免破坏官方前端；调用方应显式传参。
3. **`transfer.*` 的失败用 `ok:false` 表达**：`transfer.begin/chunk/end` 的参数错误回执是 `{"ok": false, "error": ...}`，指令状态仍是 `SUCCESS`，与其它指令的 `E_PARAM` 语义不统一（客户端需读 `result.ok`）。
4. 无 TLS：仅回环监听，可接受。
5. 本报告未覆盖 Windows 以外的平台行为（代码无平台分支）。

---

## 5. 版本与文件

- Blender 插件：`1.1.7` → **`1.1.8`**（`__init__.py:23,31`），打包为 `DSH_Blender_Bridge_Addon_v1.1.8-fixed.zip`。
- DSH bundle：`dsh-blender-bridge` **1.2.1**（原生 bundle，3 个工具 + 状态胶囊）。
- 上游 `src/dsh_plugin` 自创 `manifest.json` 格式、依赖不存在的 `window.DSH` 宿主 API，**不是** DSH 插件，无法通过 DSH 插件管理器安装 —— 故重写为原生 bundle。

---

## 6. 建议

1. 想更安全：Blender 面板设 `auth_token`，DSH 侧 bundle 配置写同一个 `token`（`Sec-WebSocket-Protocol: dsh-bridge,<token>` 已支持并实测）。
2. 需要多客户端：把 `max_connections` 调到实际并发数（已修 off-by-one，配置值即实际可用数）。
3. 想给上游提 PR：A1/A2 是必现的 Blender 5.x 兼容问题；V13（`dsh-app://app`）是 DSH 宿主专用的 Origin 白名单项。
