# 架构设计文档

## 一、总体架构

```
┌────────────────────────────── DSH 插件端（前端）──────────────────────────────┐
│  UI 层        ui.js / index.html（上传拖拽、预览、日志、历史预设、参数面板）      │
│  状态层       store.js（配置 / 历史 / 日志 / 模板，持久化）                      │
│  传输层       transfer.js（分片 / MD5 / 断点续传 / 下行重组）                    │
│  通信层       client.js（WebSocket、心跳、自动重连、指令 Promise 化）             │
│  协议层       protocol.js（6 字段信封、校验）                                   │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                          │ ws://127.0.0.1:8765 (JSON 文本帧)
┌───────────────────────────────────────┴──────────────────────────────────────┐
│                              Blender Addon（Python）                            │
│  通信层  core/ws_server.py（线程化 RFC6455、心跳、连接注册表）                    │
│  调度层  core/queue.py（主线程队列、串行 / 并行批次） core/dispatcher.py（注册/校验/兜底）│
│  传输层  core/transfer.py（会话、分片合并、MD5 校验、出站切分）                  │
│  解析层  ai/（base 抽象 / mock 兜底 / http 远端 / registry 降级）                │
│  执行层  handlers/（modeling character animation effects material render scene export nl pipeline addons）│
│  适配层  compat/（4.2 ~ 5.3 API 差异隔离）                                      │
│  工具层  utils/（logger 分级滚动、backup 环形槽位、paths 跨平台、内存/临时清理）   │
│  UI 层   operators.py / panel.py（侧边栏面板与操作符）                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 二、线程模型

- **网络线程**：`WSServer` 独立 accept 线程 + 每连接处理线程，只做帧编解码与入队；
- **主线程落地**：`bpy.app.timers` 100ms 节拍从队列取指令，在主线程调用 `bpy.ops`，避免上下文错误；
- **处理器内异步事件**：通过 `bridge.push_event` 广播进度 / 预览，不阻塞当前指令；
- **锁**：连接注册表、分片会话、指令队列均有独立锁，单连接异常不影响服务整体。

## 三、请求生命周期

```
DSH client.send(cmd_type, payload)
  → new_command 生成信封
  → WebSocket 文本帧
  → Blender WSServer 解码 → validate_envelope
  → 系统指令直接应答；业务指令入 CommandQueue
  → 主线程定时器 drain → Dispatcher.execute
      → 参数校验 → 处理器执行 → 结果/异常收敛为回执
  → send_text 回传 → DSH pending map 按 cmd_id resolve/reject
```

## 四、可靠性设计

| 风险 | 对策 |
|---|---|
| 大文件损坏 | 分片 + MD5 校验 + 断点续传 |
| 网络抖动 | 30s 心跳、超时断开、指数退避自动重连 |
| 处理器崩溃 | 顶层兜底捕获，转 FAILED 回执，不拖垮线程 |
| 误操作破坏场景 | 自动备份环形槽位 + 清单回滚 |
| 内存溢出 | 批量操作分批（batch_size）、闲置临时文件清理 |
| 版本 API 差异 | compat 层集中映射，低版本静默降级 |
| 配置丢失 | 默认配置 + 用户配置合并，损坏回退默认值 |
| 第三方算子误调用 | 算子存在性校验、参数类型白名单过滤、顶层异常兜底、`allow_addon_invoke` 总开关 |

## 五、数据持久化

| 数据 | 位置 |
|---|---|
| 用户运行配置 | `config/runtime_config.json` |
| 日志 | `DSH_Bridge/logs/`，按天滚动保留 14 天 |
| 场景备份 | `DSH_Bridge/backups/`，环形覆盖 |
| 材质预设 | `DSH_Bridge/presets/*.json` |
| DSH 端历史 / 设置 | 宿主存储或 localStorage |

## 六、扩展点

- 新指令：处理器 + 注册 + 协议常量，三处即可挂载；
- 新 AI 后端：继承抽象基类并注册；
- 新渲染通道 / 贴图类型：在 material 处理器节点树中扩展；
- 新导出格式：在 export 层增加算子调用并复用出站分片回传；
- 第三方插件生态：`handlers/addons.py` 枚举已启用 Addon，按关键词表归类能力；新增能力分类只需扩展 `CAPABILITY_KEYWORDS`；算子发现基于 `bpy.types.Operator` 子类遍历与 ID 前缀归属，通用调用入口复用 dispatcher 异常兜底。
