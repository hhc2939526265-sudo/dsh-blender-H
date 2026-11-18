# 开发接口文档

## 一、通信协议

### 1.1 连接

- 传输：本地 WebSocket 长连接，默认 `ws://127.0.0.1:8765`（仅绑定回环地址，不对外暴露）
- 编码：UTF-8 JSON 文本帧
- 心跳：应用层 `system.heartbeat`，30s 间隔；服务端回执 Pong 结果；超时 10s 判定断线
- 握手：连接建立后客户端发送 `system.handshake`，服务端回执携带服务端版本与已注册指令清单
- 握手安全：
  - Origin 白名单：浏览器网页发起的连接会携带 `Origin` 头，本地回环（localhost / 127.0.0.1 / ::1）默认放行，其余主机需在配置 `allowed_origins` 中显式加入；无 `Origin` 头的桌面客户端不受限制。
  - 共享口令：配置 `auth_token` 非空时，客户端须通过 `Sec-WebSocket-Protocol: dsh-bridge,<token>` 或 `Authorization: Bearer <token>` 携带同一口令，否则握手返回 403。
  - 连接数：`max_connections` 限制并发连接数，超出后新连接被拒绝。

### 1.2 消息信封（固定 6 字段）

```json
{
  "cmd_id": "uuid-v4",
  "cmd_type": "mesh.add_primitive",
  "payload": { },
  "status": "PENDING | RUNNING | SUCCESS | FAILED | CANCELED",
  "result": { },
  "error": { "code": "", "message": "", "detail": "" }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| cmd_id | string | 指令唯一 ID，回执原样带回，用于 Promise 关联 |
| cmd_type | string | 指令类型，见下方指令集 |
| payload | object | 参数体，结构按指令定义 |
| status | string | 执行状态枚举 |
| result | object | 成功返回结果；失败为空对象 |
| error | object | `code / message / detail`，无错误时为空串 |

### 1.3 错误码

| code | 含义 |
|---|---|
| E_PROTOCOL | 信封结构 / 字段非法 |
| E_JSON | 报文不是合法 JSON |
| E_PARAM | 缺少必填参数或类型错误 |
| E_UNKNOWN_CMD | 未注册的指令类型 |
| E_EXEC | 处理器执行异常 |
| E_FATAL | 顶层兜底异常 |
| E_TRANSFER | 分片缺失 / MD5 校验失败 |

### 1.4 批量队列

- 指令按 FIFO 入队；`serial` 每节拍执行 1 条，`parallel` 每节拍最多 `max_parallel` 条；
- 排队等待超时 `command_timeout`（默认 120s）：条目在队列中等待超时即被丢弃；Blender 主线程不可抢占，正在执行的指令无法中途中断；
- 回执 `result._elapsed_ms` 记录执行耗时。

## 二、分片传输协议

### 2.1 上行（客户端 → Blender）

| 指令 | payload | 回执 result |
|---|---|---|
| transfer.begin | `file_id, filename, total_size, md5, chunk_count` | `resumed, missing[], received, chunk_count` |
| transfer.chunk | `file_id, index, data(base64)` | `ok, received, chunk_count` |
| transfer.end | `file_id` | `ok, path, filename, size, md5` |

- 分片大小默认 64KB；重连后 `begin` 返回缺失索引，仅补发缺失分片；
- `end` 合并后按 MD5 校验，不一致则删除临时文件并返回 `E_TRANSFER`。

### 2.2 下行（Blender → 客户端）

Blender 主动推送同构三阶段消息：`transfer.begin`（含 meta）→ 多帧 `transfer.chunk`
→ `transfer.end`；客户端按 `file_id` 重组为 Blob 并生成预览。

## 三、指令集大全

### 3.1 系统 / 传输

| cmd_type | 说明 | 关键参数 |
|---|---|---|
| system.handshake | 握手能力协商 | - |
| system.heartbeat | 心跳 | - |
| system.stop | 清空排队指令 | - |
| system.shutdown | 关闭桥接服务（回执后延迟停止） | - |
| system.pong | 预留：心跳 Pong 回执，当前由服务端协议层自动应答 | - |
| transfer.begin / chunk / end | 分片传输 | 见 2.1 |
| transfer.ack | 预留：分片确认回执，当前协议未使用 | - |
| render.result_back | 预留：渲染结果主动回传事件，当前由 `transfer.end` 事件承载 | - |

### 3.2 建模指令（35 种）

| cmd_type | 说明 | 必填参数 |
|---|---|---|
| mesh.add_primitive | 基础几何体 | type（cube/sphere/ico_sphere/cylinder/cone/torus/plane/grid/monkey） |
| mesh.boolean | 布尔运算 | target, operand, operation |
| mesh.extrude | 挤出 | object, amount |
| mesh.loop_cut | 环切 | object, cuts |
| mesh.bevel | 倒角 | object, width, segments |
| mesh.array | 阵列 | object, count |
| mesh.curve | 曲线 | points[[x,y,z]] |
| mesh.solidify | 实体化 | object, thickness |
| mesh.remesh | 重网格化 | object, voxel_size |
| mesh.inset | 内插面 | object, thickness |
| mesh.subdivide | 细分 | object, levels |
| mesh.decimate | 面数精简 | object, ratio |
| mesh.recalc_normals | 法线统一 | object |
| mesh.origin_set | 原点归位 | object, target |
| mesh.align | 吸附对齐 | object, target, axis |
| mesh.flip_normals | 法线翻转 | object |
| mesh.rename | 重命名 | object, new_name |
| mesh.batch_generate | 参数化批量生成 | count, type, location_range, scale_range |
| mesh.delete | 删除对象 | objects[] |
| mesh.select | 选择 | objects[] / mode=ALL |
| mesh.mirror | 镜像 | object, axis |
| mesh.weld | 按距离合并顶点 | object, distance |
| mesh.smooth | 平滑着色 | object |
| mesh.uv_unwrap | UV 自动展开 | object |
| mesh.apply_all | 应用全部修改器 | object |
| mesh.transform | 变换 | object, location/rotation/scale |
| mesh.duplicate | 复制对象（可关联 / 独立数据） | object, linked, name |
| mesh.join | 合并多对象到目标 | object, objects[] |
| mesh.separate | 按松散块 / 材质 / 选择分离 | object, type |
| mesh.screw | 螺旋修改器 | object, angle, steps, iterations |
| mesh.wireframe | 线框修改器 | object, thickness, offset |
| mesh.displace | 置换起伏 | object, strength, direction |
| mesh.edge_split | 锐边拆分 | object, split_angle |
| mesh.shrinkwrap | 收缩包裹到目标表面 | object, target, wrap_method |
| mesh.crease | 边折痕标记 | object, edges[], value |

### 3.3 角色建模

| cmd_type | 说明 | 必填参数 |
|---|---|---|
| character.build | 图片驱动建模 | image_paths[], quality |
| character.rig | 骨骼自动绑定 | object |
| character.shape_keys | 写入面部形状键 | object, shape_keys[] |
| character.uv_bake | 参考图 PBR 烘焙 | object, image_path |

### 3.4 动画指令（17 种）

| cmd_type | 说明 | 必填参数 |
|---|---|---|
| anim.keyframe | 位移 / 旋转 / 缩放关键帧 | object, mode, frames[[frame, values]] |
| anim.rig_auto | 自动骨骼绑定 | object, skeleton |
| anim.loop_cycle | 走 / 跑 / 跳循环 | object, cycle |
| anim.physics | 刚体 / 柔体 / 布料 / 流体 | object, kind |
| anim.path_constraint | 路径约束 | object, points[] |
| anim.mocap_apply | 动捕轨迹对齐 | object, motion |
| anim.timing | 全局 / 局部变速 | object, speed |
| anim.easing | 缓动曲线 | object, easing |
| anim.clear | 清除对象动画数据 | object |
| anim.ik | 骨骼 IK 约束 | object, bone, target, chain_count |
| anim.copy_transform | 复制变换约束 | object, target, influence |
| anim.action_list | 列出场景动作数据 | 可选 object |
| anim.parent_set | 对象父子绑定 | object, parent, keep_transform |
| anim.bone_keyframe | 单骨骼关键帧 | object, bone, frame, rotation/location |
| anim.pose | 批量骨骼战斗姿态 | object, poses{bone:{rotation,location}}, frame |
| anim.follow_target | 目标跟随约束 | object, target, constraint, bone, influence |
| anim.action_mix | 动作层混合权重规格 | object, layers[{action,weight}] |

### 3.5 特效指令（18 种）

| cmd_type | 说明 |
|---|---|
| effect.particle | 粒子系统（数量 / 速度 / 生命周期 / 颜色渐变） |
| effect.glow | 发光材质 + 合成辉光 |
| effect.fluid | 流体域参数 |
| effect.deform | 晶格 / 形状键形变关键帧 |
| effect.camera_match | 摄像机动画（推拉摇移 / 环绕） |
| effect.force_field | 力场（风 / 推力 / 涡旋 / 湍流等） | object, kind, field.strength |
| effect.light | 灯光对象（点 / 平行 / 聚光 / 面光） | type, energy, color, location |
| effect.world | 世界环境背景色 / 强度 | color, strength |
| effect.hair | 毛发粒子（数量 / 长度 / 颜色） | object, hair.count/length |
| effect.motion_blur | 合成运动模糊 | enabled, factor |
| effect.trail | 剑气 / 身法运动拖尾 | object, trail.length/width/color |
| effect.shockwave | 环形冲击波扩散 | object, shockwave.timing/max_radius/color |
| effect.shield | 能量护盾球壳 | object, shield.radius/color/alpha |
| effect.lightning | 雷弧闪电折线 | start, end, segments, lightning.color |
| effect.aura | 周身灵气光环脉动 | object, aura.radius/color/cycle |
| effect.debris | 碎石碎片刚体飞溅 | object, debris.count/size/speed |
| effect.spark | 火花迸发粒子 | object, spark.count/speed/life/color |
| effect.camera_shake | 镜头震动 | amplitude, end_frame, frequency |

### 3.6 材质指令（10 种）

| cmd_type | 说明 | 必填参数 |
|---|---|---|
| material.pbr_generate | PBR 节点树生成 | object, base_color/metallic/roughness/alpha |
| material.batch_replace | 批量替换材质 | objects[], material_name |
| material.batch_adjust | 批量调整参数 | objects[], params |
| material.preset_save | 保存材质预设 | name, object |
| material.preset_load | 加载材质预设 | name, object |
| material.duplicate | 复制材质并挂载目标 | object（可选 target/new_name） |
| material.assign | 把已有材质分配给对象 | object, material_name, replace |
| material.clear | 清空对象材质槽 | object |
| material.list | 材质清单（对象挂载 + 场景全部材质） | 可选 objects[] |
| material.emission | 自发光能量材质 | object, color, strength, alpha |

### 3.7 渲染 / 场景 / 导出

| cmd_type | 说明 |
|---|---|
| render.switch_engine | 切换 Eevee / Cycles |
| render.settings | 分辨率 / 采样 / 帧范围 / 输出路径 |
| render.execute | 执行渲染并回传成品 |
| scene.backup | 场景备份 |
| scene.rollback | 回滚备份 |
| scene.export / scene.import | 工程导出 / 导入 |
| export.asset | 网格资产 glb 回传 |
| export.animation | 骨骼轨迹 JSON + glb 回传 |
| export.material | 材质参数回传 |
| export.scene | 全场景 glb 回传 |
| nl.dispatch | 自然语言解析并执行 |
| pipeline.character | 图片 → 角色一键流水线 |
| pipeline.video | 视频 → 动作 + 特效流水线 |
| pipeline.iterate | 资产回传进入下一轮迭代 |

### 3.8 第三方插件生态（4 种）

识别并调用 Blender 中已启用的第三方 Addon：读取插件元信息、按关键词归类能力、
发现其注册的算子（Operator），并通过通用入口安全调用。

| cmd_type | 说明 | 必填参数 |
|---|---|---|
| addon.list | 枚举全部已启用第三方插件，返回元信息、能力分类与算子数量 | - |
| addon.detail | 查询单个插件的完整元信息与算子参数定义 | `module` |
| addon.invoke | 通用算子调用入口 | `operator`（`namespace.operator`） |
| addon.match | 按自然语言意图匹配最贴合的插件 | `intent` |
| addon.enable | 运行时启用指定第三方插件（无需重启 Blender） | `module` |
| addon.disable | 运行时禁用指定第三方插件 | `module` |
| addon.status | 插件生态自检：已启用清单、版本与调用策略开关 | - |
| addon.operator_search | 跨全部已注册算子按关键词检索（ID / 标签） | `keyword`, 可选 `top_n` |
| addon.operator_batch | 对一批对象依次套用同一算子，逐个隔离异常回执 | `operator`, `objects`, 可选 `params` / `per_object` |
| addon.nodegroup_apply | 把已有几何节点组挂到对象上，可覆写输入 | `node_group`, 可选 `object` / `inputs` |

**addon.list 回执 result**

```json
{
  "total": 3,
  "capabilities": { "rigging": ["rigify_pro"], "effects": ["fire_helper"] },
  "addons": [{
    "module": "rigify_pro",
    "name": "Rigify Pro",
    "author": "Author",
    "version": "1.2.0",
    "category": "Rigging",
    "capability": "rigging",
    "description": "自动骨骼绑定与权重",
    "operator_count": 6
  }]
}
```

**addon.invoke payload**

```json
{
  "operator": "rigify_pro.generate_rig",
  "params": { "target": "Character", "use_mirror": true },
  "mode": "execute"
}
```

- `mode`：`execute`（直接执行，默认）/ `invoke`（弹出算子交互面板 `INVOKE_DEFAULT`）；
- `params` 仅允许 JSON 原始类型（字符串 / 整数 / 浮点 / 布尔 / 原始类型数组），嵌套对象会被拒绝；
- 能力分类取值：`modeling / rigging / animation / effects / material / render / asset / io / other`；
- 调用开关：配置 `allow_addon_invoke=false` 时禁止调用第三方算子；单插件算子暴露上限 `addon_max_operators_per_addon`。

**addon.operator_batch payload**

```json
{
  "operator": "object.shade_smooth",
  "objects": ["Cube", "Sphere", "active"],
  "params": {},
  "per_object": { "Cube": { "use_auto_smooth": true } }
}
```

- 批量套用同一算子到多个对象；单对象失败不中断整批，回执逐条给出 `SUCCESS / FAILED` 与错误信息；
- `per_object` 可按对象名覆盖该对象的算子参数；算子安全策略（总开关 / 黑名单 / 白名单）与 `addon.invoke` 一致。

**addon.nodegroup_apply payload**

```json
{
  "object": "active",
  "node_group": "Procedural_Rock",
  "inputs": { "Density": 3.0, "Seed": 7 }
}
```

- 几何节点组需已存在于 `bpy.data.node_groups`（由已启用插件或资产库导入）；`inputs` 按节点组输入套接字名称覆写默认值。

**启停与检索**

- `addon.enable` / `addon.disable`：模块名仅允许字母 / 数字 / 下划线 / 点号；桥接自身不可被启停；分别受配置 `allow_addon_enable` / `allow_addon_disable` 控制。
- `addon.operator_search`：返回算子 `idname`、`label`、归属 `prefix`；`addon.status` 回执含 Blender 版本、已启用模块与当前策略开关。

## 四、多模态数据格式

### 4.1 角色规格（AI → Blender）

```json
{
  "quality": "medium",
  "proportions": { "height": 1.75, "shoulder_width": 0.45 },
  "features": { "face": "oval", "eyes": "normal" },
  "clothing": [{ "part": "top", "category": "cloth", "color": [0.3,0.3,0.3,1], "roughness": 0.8 }],
  "hair": { "style": "short", "color": [0.05,0.04,0.03,1] },
  "skin_color": [0.82, 0.66, 0.55, 1],
  "shape_keys": ["jaw_open", "brow_inner_up"]
}
```

### 4.2 动作规格

```json
{
  "fps": 24,
  "joints": ["hips", "spine", "chest", "neck", "head", "...21+"],
  "frames": [{ "index": 0, "rotations": { "hips": [0,0,0] }, "positions": { "hips": [0,0,0.9] } }],
  "confidence": 0.6,
  "loop": true
}
```

### 4.3 特效规格

```json
{
  "particles": [{ "count": 200, "speed": 1.0, "life": 2.0, "color_start": [1,0.6,0.2,1], "color_end": [0.2,0.4,1,1] }],
  "glow": [{ "intensity": 1.5, "color": [1,0.7,0.3,1], "motion": "radial" }],
  "fluid": [{ "shape": "smoke", "velocity": 0.6, "collision": true }],
  "deform": [{ "amplitude": 0.2, "timing": [0, 24] }],
  "camera": { "trajectory": "push", "distance": 3.0, "fov": 50 }
}
```

## 五、外部 AI 服务对接

推理网关接收如下 JSON（`POST {endpoint}`），返回 `{ "result": {...规格字典} }` 或
`{ "error": "..." }`：

```json
{ "method": "analyze_character", "payload": { "images": [], "params": {} } }
```

| method | 入参 | 返回 |
|---|---|---|
| analyze_character | images[], params | 角色规格 |
| analyze_motion | video, params | 动作规格 |
| analyze_effect | video, params | 特效规格 |
| parse_nl | prompt, params | `{ commands: [{ cmd_type, payload }] }` |

## 六、二次扩展开发

### 6.1 新增一条建模指令

1. 在 `handlers/modeling.py` 编写处理器：`def my_op(payload, ctx) -> dict`；
2. 文件底部 `register()` 中 `dispatcher.register("mesh.my_op", my_op, ["必填参数"])`；
3. 在 `core/protocol.py` 的 `CommandType` 增加常量；
4. DSH 端按信封结构直接 `client.send("mesh.my_op", payload)`。

### 6.2 新增 AI 后端

1. 继承 `ai/base.py::BaseAIProvider`，实现四个解析方法；
2. 在 `ai/registry.py` 注册新后端名；
3. 配置 `ai.provider` 切换；远端异常自动降级 Mock。

### 6.3 目录分层

```
通信层  core/ws_server.py、core/queue.py
协议层  core/protocol.py、core/transfer.py
解析层  ai/
执行层  handlers/
适配层  compat/
工具层  utils/
UI 层   operators.py、panel.py
```

### 6.4 约束

- 业务代码禁止硬编码魔法数字，统一走 `config/default_config.py`；
- 处理器异常必须收敛为 FAILED 回执，不得抛到网络线程；
- 仅使用 Blender 内置库与标准库；必需依赖须内置静默安装逻辑。
