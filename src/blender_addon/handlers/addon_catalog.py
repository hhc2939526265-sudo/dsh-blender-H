# -*- coding: utf-8 -*-
"""
常用第三方 Blender 插件目录（离线元信息映射）。

本目录不读取第三方插件源码，也不假设其算子 ID 一定存在；
作用是：
- 按能力 / 别名把用户提到的常用插件归类到桥接能力体系；
- 给出该插件在本桥接内推荐走的内置指令（bridge_commands）；
- 插件在真机启用后，具体算子 ID 仍以 ``addon.detail`` /
  ``addon.operator_search`` 实时发现的结果为准。

能力取值与 ``addons.classify_addon`` 保持一致：
modeling / rigging / animation / effects / material / render / asset / io / other。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 已知插件目录：顺序即展示顺序
# ---------------------------------------------------------------------------
KNOWN_PLUGINS: List[Dict[str, Any]] = [
    {
        "key": "mpfb2",
        "name": "MPFB2",
        "aliases": ["mpfb", "mpfb2", "makehuman", "人物生成器", "人形建模"],
        "capability": "modeling",
        "category": "角色生成",
        "workflow": "参考图 / 基础人形 → 体型五官 → 拓扑网格 → 材质与绑定",
        "bridge_commands": [
            {"cmd": "character.build", "note": "生成标准人体拓扑与基础形体"},
            {"cmd": "character.uv_bake", "note": "UV 展开与基础 PBR 烘焙"},
        ],
        "notes": "人形生成类插件；真人像细节需结合外部 AI 解析结果。",
    },
    {
        "key": "jiggle_physics",
        "name": "Jiggle Physics",
        "aliases": ["jiggle", "jiggle physics", "抖动", "软体晃动", "物理摆动"],
        "capability": "effects",
        "category": "软体物理",
        "workflow": "选中软体部位 → 软体修改器 → 质量 / 刚度参数 → 烘焙关键帧",
        "bridge_commands": [
            {"cmd": "anim.physics", "note": "kind=soft 软体物理，mass / 刚度参数可调"},
        ],
        "notes": "抖动 / 软体类效果；真机软体刚度与碰撞需在 Blender 内微调。",
    },
    {
        "key": "bagapie",
        "name": "BagaPie",
        "aliases": ["bagapie", "模型库", "素材库", "资产包", "资产库"],
        "capability": "asset",
        "category": "模型资产库",
        "workflow": "检索资产 → 导入场景 → 摆放 / 缩放 → 材质衔接",
        "bridge_commands": [
            {"cmd": "scene.import", "note": "导入插件 / 资产库提供的模型资产"},
            {"cmd": "export.asset", "note": "回传资产清单供 DSH 侧复用"},
        ],
        "notes": "资产库类插件；资产本体由插件资源提供，桥接负责导入与摆放。",
    },
    {
        "key": "sword_trail",
        "name": "Sword Trail",
        "aliases": ["sword trail", "武器拖尾", "刀光", "剑 trail", "兵刃残影"],
        "capability": "effects",
        "category": "武器特效",
        "workflow": "绑定武器 → 拖尾曲线 / 粒子 → 发光材质 → 跟随武器运动",
        "bridge_commands": [
            {"cmd": "effect.trail", "note": "武器运动拖尾，长度 / 宽度 / 颜色可调"},
            {"cmd": "material.emission", "note": "拖尾自发光材质"},
        ],
        "notes": "武器拖尾类特效；与 anim.follow_target 配合让拖尾跟随武器。",
    },
    {
        "key": "extra_nodes",
        "name": "Extra Nodes",
        "aliases": ["extra nodes", "节点扩展", "节点组库", "几何节点扩展"],
        "capability": "asset",
        "category": "几何节点库",
        "workflow": "选择节点组 → 挂到对象 → 覆写输入参数 → 查看结果",
        "bridge_commands": [
            {"cmd": "addon.nodegroup_apply", "note": "挂载已有几何节点组并覆写输入"},
        ],
        "notes": "节点组需先由插件导入到 bpy.data.node_groups 后再挂载。",
    },
    {
        "key": "simply_cloth",
        "name": "Simply Cloth",
        "aliases": ["simply cloth", "布料", "衣料", "布料物理"],
        "capability": "effects",
        "category": "布料物理",
        "workflow": "选中布料网格 → 布料修改器 → 质量 / 碰撞 → 烘焙解算",
        "bridge_commands": [
            {"cmd": "anim.physics", "note": "kind=cloth 布料修改器，mass 参数可调"},
        ],
        "notes": "布料碰撞与解算精度需真机调参；烘焙关键帧由解算器落地。",
    },
    {
        "key": "alt_tab_easy_fog2",
        "name": "Alt Tab Easy Fog2",
        "aliases": ["easy fog", "easy fog2", "体积雾", "雾效", "大气", "烟雾氛围"],
        "capability": "effects",
        "category": "大气雾效",
        "workflow": "雾效体积 → 密度 / 颜色 / 范围 → 世界与灯光衔接",
        "bridge_commands": [
            {"cmd": "effect.fluid", "note": "流体 / 体积占位，形态与速度参数映射"},
            {"cmd": "effect.world", "note": "世界环境雾色与背景氛围"},
        ],
        "notes": "体积雾最终表现依赖真机体积着色器与灯光设置。",
    },
    {
        "key": "auto_rig_pro",
        "name": "Auto-Rig Pro",
        "aliases": ["auto rig pro", "arp", "自动绑定", "骨骼绑定", "自动骨骼"],
        "capability": "rigging",
        "category": "自动绑定",
        "workflow": "骨架对齐 → 自动生成骨骼 → 权重分配 → 姿态 / 动作驱动",
        "bridge_commands": [
            {"cmd": "anim.rig_auto", "note": "标准人形自动骨骼与权重分配"},
            {"cmd": "character.rig", "note": "角色骨架挂载与骨骼联动"},
        ],
        "notes": "绑定结果权重需在真机刷写微调；跨插件骨架命名以真机为准。",
    },
    {
        "key": "faceit",
        "name": "Faceit",
        "aliases": ["faceit", "面部绑定", "表情绑定", "表情键", "面部形状键"],
        "capability": "rigging",
        "category": "面部表情",
        "workflow": "面部网格 → 形状键 / 表情单元 → 面部骨骼联动",
        "bridge_commands": [
            {"cmd": "character.shape_keys", "note": "面部形状键 / 表情单元生成"},
        ],
        "notes": "表情单元数量与命名以真机插件生成结果为准。",
    },
    {
        "key": "simply_cloth_studio_2",
        "name": "Simply Cloth Studio 2",
        "aliases": ["cloth studio", "cloth studio 2", "布料套件", "服装物理", "套装布料"],
        "capability": "effects",
        "category": "布料套件",
        "workflow": "服装分片 → 布料参数 → 碰撞体 → 批量布料解算",
        "bridge_commands": [
            {"cmd": "anim.physics", "note": "kind=cloth 布料修改器，支持批量对象套用"},
        ],
        "notes": "套件级布料流程；多件服装可用 addon.operator_batch 批量触发。",
    },
    {
        "key": "hair_pro",
        "name": "Hair Pro",
        "aliases": ["hair pro", "毛发", "头发", "发型", "发丝"],
        "capability": "effects",
        "category": "毛发",
        "workflow": "头皮面 → 毛发粒子 → 长度 / 数量 / 颜色 → 风场吹动",
        "bridge_commands": [
            {"cmd": "effect.hair", "note": "毛发粒子数量 / 长度 / 颜色生成"},
            {"cmd": "effect.force_field", "note": "风场吹动发丝摆动"},
        ],
        "notes": "毛发密度与走向需真机毛发工具细化。",
    },
    {
        "key": "animcraft",
        "name": "Animcraft",
        "aliases": ["animcraft", "动画工具", "动作编辑", "动画循环"],
        "capability": "animation",
        "category": "动画编辑",
        "workflow": "动作片段 → 关键帧 / 姿态 → 循环衔接 → 曲线调速",
        "bridge_commands": [
            {"cmd": "anim.keyframe", "note": "位移 / 旋转 / 缩放关键帧"},
            {"cmd": "anim.pose", "note": "批量骨骼姿态"},
            {"cmd": "anim.loop_cycle", "note": "动作循环与首尾衔接"},
        ],
        "notes": "动作库片段导入后由桥接对齐到当前骨架。",
    },
    {
        "key": "geo_scatter",
        "name": "Geo-Scatter",
        "aliases": ["geo-scatter", "geoscatter", "scatter", "散布", "植被散布", "阵列分布"],
        "capability": "asset",
        "category": "几何散布",
        "workflow": "散布面 → 实例对象 → 密度 / 随机缩放旋转 → 批量生成",
        "bridge_commands": [
            {"cmd": "mesh.array", "note": "阵列分布基础排布"},
            {"cmd": "mesh.batch_generate", "note": "参数范围随机化批量生成差异化资产"},
        ],
        "notes": "真机散布密度 / 权重贴图由插件几何节点控制；桥接给出批量生成底座。",
    },
    {
        "key": "rockforms",
        "name": "RockForms",
        "aliases": ["rockforms", "岩石", "石头", "岩体", "岩块"],
        "capability": "modeling",
        "category": "岩石造型",
        "workflow": "基础形体 → 置换 / 重拓扑 → 细节雕刻 → 法线烘焙",
        "bridge_commands": [
            {"cmd": "mesh.displace", "note": "置换修改器塑造岩体起伏"},
            {"cmd": "mesh.remesh", "note": "重拓扑规整岩石网格"},
        ],
        "notes": "岩石细节噪声参数需真机调整。",
    },
    {
        "key": "true_terrain",
        "name": "True Terrain",
        "aliases": ["true terrain", "terrain", "地形", "山地", "地貌", "山形"],
        "capability": "modeling",
        "category": "地形生成",
        "workflow": "地形平面 → 细分 → 高度置换 → 沟壑 / 山体成型",
        "bridge_commands": [
            {"cmd": "mesh.subdivide", "note": "细分提供地形高度网格密度"},
            {"cmd": "mesh.displace", "note": "高度置换生成山体起伏"},
        ],
        "notes": "地形纹理与植被衔接可接材质 / 散布指令。",
    },
    {
        "key": "nexus",
        "name": "NeXus",
        "aliases": ["nexus", "合并网格", "硬表面工具", "网格合并"],
        "capability": "modeling",
        "category": "硬表面建模",
        "workflow": "硬表面构件 → 布尔 / 合并 → 倒角 / 布线整理",
        "bridge_commands": [
            {"cmd": "mesh.join", "note": "多构件合并为整体"},
            {"cmd": "mesh.boolean", "note": "布尔加减成型"},
            {"cmd": "mesh.bevel", "note": "倒角硬表面边缘"},
        ],
        "notes": "NeXus 具体算子以真机启用后检索结果为准。",
    },
    {
        "key": "vfx_toolkit",
        "name": "VFX Toolkit",
        "aliases": ["vfx toolkit", "特效包", "视觉特效", "特效工具集"],
        "capability": "effects",
        "category": "特效工具包",
        "workflow": "粒子 / 火花 / 碎片 / 光效 → 参数映射到 Blender 系统",
        "bridge_commands": [
            {"cmd": "effect.particle", "note": "基础粒子系统"},
            {"cmd": "effect.spark", "note": "火花迸发"},
            {"cmd": "effect.debris", "note": "碎片刚体飞溅"},
        ],
        "notes": "复杂特效仍需真机解算与节点调整。",
    },
    {
        "key": "style_engine",
        "name": "Style Engine",
        "aliases": ["style engine", "风格化", "卡通材质", "渲染风格", " stylized"],
        "capability": "material",
        "category": "风格化材质",
        "workflow": "风格基调 → 材质节点树 → 自发光 / 色阶 → 渲染输出",
        "bridge_commands": [
            {"cmd": "material.pbr_generate", "note": "提示词驱动材质节点树"},
            {"cmd": "material.emission", "note": "风格化发光 / 描边类自发光"},
        ],
        "notes": "卡通 / 国风等风格结果依赖材质节点与灯光配合。",
    },
    {
        "key": "baker_wrangler",
        "name": "Baker Wrangler",
        "aliases": ["baker wrangler", "baker", "w rangler", "烘焙", "贴图烘焙", "法线烘焙"],
        "capability": "material",
        "category": "材质烘焙",
        "workflow": "UV 展开 → 烘焙颜色 / 法线 / AO / 粗糙度 → 贴图回挂",
        "bridge_commands": [
            {"cmd": "character.uv_bake", "note": "UV 展开与基础贴图烘焙"},
            {"cmd": "material.pbr_generate", "note": "烘焙结果回挂 PBR 通道"},
        ],
        "notes": "烘焙贴图通道与分辨率以真机烘焙设置为准。",
    },
    {
        "key": "light_painter",
        "name": "Light Painter",
        "aliases": ["light painter", "绘画灯光", "布光", "灯光布置", "打光"],
        "capability": "render",
        "category": "布光",
        "workflow": "主光 / 辅光 / 轮廓光 → 位置颜色能量 → 渲染预览",
        "bridge_commands": [
            {"cmd": "effect.light", "note": "点 / 平行 / 聚光 / 面光创建与参数调整"},
            {"cmd": "render.settings", "note": "光照方案与渲染参数配置"},
        ],
        "notes": "灯光氛围需结合渲染器与世界环境调整。",
    },
]


def _haystack(entry: Dict[str, Any]) -> str:
    """拼接条目可检索文本（名称 / 别名 / 分类 / 工作流）。"""
    return " ".join([
        entry["name"], entry["key"], " ".join(entry.get("aliases", [])),
        entry.get("category", ""), entry.get("workflow", ""),
    ]).lower()


def query_catalog(capability: Optional[str] = None,
                  keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    按能力分类 / 关键词检索已知插件目录。

    :param capability: 能力标识精确过滤；为空表示不限
    :param keyword: 名称 / 别名 / 分类模糊匹配；为空表示不按关键词过滤
    :return: 命中条目列表（保持目录原始顺序）
    """
    kw = (keyword or "").strip().lower()
    result: List[Dict[str, Any]] = []
    for entry in KNOWN_PLUGINS:
        if capability and entry["capability"] != capability:
            continue
        if kw and kw not in _haystack(entry):
            continue
        result.append(entry)
    return result


def catalog_match(intent: str, top_n: int = 5) -> List[Dict[str, Any]]:
    """按自然语言意图对目录条目打分，返回最贴合的若干条目。"""
    intent = (intent or "").strip().lower()
    if not intent:
        return []
    scored: List[Dict[str, Any]] = []
    for entry in KNOWN_PLUGINS:
        score = 0
        matched: List[str] = []
        hay = _haystack(entry)
        for token in entry.get("aliases", []) + [entry["name"], entry["category"]]:
            token_low = token.lower()
            if token_low and token_low in intent:
                score += 2
                matched.append(token)
        if score <= 0:
            # 退化为双向子串包含：意图词命中条目文本
            if intent in hay:
                score = 1
        if score > 0:
            scored.append({**entry, "score": score, "matched": matched})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_n]
