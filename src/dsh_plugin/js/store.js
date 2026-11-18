/*
 * 前端状态仓库（DSH 端）。
 * 集中管理：连接状态、参数配置、执行历史、分级日志、内置场景模板。
 * 配置与历史持久化到宿主存储 / localStorage。
 */
(function (global) {
  "use strict";

  const Adapter = global.DSHAdapter;

  const DEFAULT_SETTINGS = {
    blender_path: "",
    host: "127.0.0.1",
    port: 8765,
    auto_reconnect: true,
    heartbeat_interval: 30,
    mesh_quality: "medium",
    mocap_confidence: 0.6,
    effect_strength: 0.8,
    animation_fps: 24,
    render_engine: "EEVEE",
    render_samples: 64,
    auto_backup: true,
    log_level: "INFO",
  };

  // 12+ 内置场景模板
  const PRESETS = [
    { id: "char_single", name: "单图角色建模", desc: "正面人物照 → 标准人体 + 骨骼绑定 + PBR 材质", tab: "character", payload: { quality: "medium" } },
    { id: "char_multi", name: "多图角色参考", desc: "多角度照片融合，提升体型与服装还原度", tab: "character", payload: { quality: "high" } },
    { id: "anim_walk", name: "行走动作复刻", desc: "参考视频提取 21 关节轨迹，对齐角色骨骼", tab: "motion", payload: { kind: "mocap", cycle: "walk" } },
    { id: "anim_run", name: "跑步动作复刻", desc: "高速步态轨迹复刻，自动帧率匹配与降噪", tab: "motion", payload: { kind: "mocap", cycle: "run" } },
    { id: "anim_jump", name: "跳跃循环动画", desc: "起跳 / 腾空 / 落地三段式循环关键帧", tab: "motion", payload: { kind: "mocap", cycle: "jump" } },
    { id: "fx_particle", name: "粒子火焰特效", desc: "粒子数量 / 速度 / 生命周期 / 颜色渐变还原", tab: "motion", payload: { kind: "effect", effect: "particle" } },
    { id: "fx_glow", name: "辉光能量特效", desc: "发光材质 + 合成辉光节点，强度与颜色可调", tab: "motion", payload: { kind: "effect", effect: "glow" } },
    { id: "fx_fluid", name: "烟雾流体特效", desc: "流体域参数映射，形态 / 速度 / 碰撞还原", tab: "motion", payload: { kind: "effect", effect: "fluid" } },
    { id: "fx_deform", name: "形变呼吸动画", desc: "晶格 / 形状键形变，幅度与时序对齐原片", tab: "motion", payload: { kind: "effect", effect: "deform" } },
    { id: "fx_camera", name: "环绕镜头匹配", desc: "解析推拉摇移轨迹，生成摄像机动画", tab: "motion", payload: { kind: "effect", effect: "camera" } },
    { id: "mat_metal", name: "金属 PBR 材质", desc: "高金属度低粗糙度，提示词驱动节点树", tab: "material", payload: { metallic: 0.9, roughness: 0.25 } },
    { id: "mat_cloth", name: "布料 PBR 材质", desc: "高粗糙度织物材质，可衔接布料物理", tab: "material", payload: { metallic: 0.0, roughness: 0.85 } },
    { id: "render_still", name: "产品静帧渲染", desc: "Eevee 快速出图，成品自动回传预览", tab: "material", payload: { engine: "EEVEE" } },
    { id: "iter_roundtrip", name: "回传二次迭代", desc: "Blender 资产回传 DSH，AI 继续优化建模 / 动画", tab: "history", payload: { action: "export" } },
  ];

  const LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"];

  class Store {
    constructor() {
      this.status = "disconnected"; // disconnected / connecting / connected / error
      this.statusDetail = "";
      this.settings = Object.assign({}, DEFAULT_SETTINGS, Adapter.loadJSON("settings", {}));
      this.history = Adapter.loadJSON("history", []);
      this.logs = [];
      this.stats = { pending: 0, success: 0, failed: 0 };
      this.provider = "-";
      this.previews = {};
    }

    // --------------------------------------------------------- 设置
    getSetting(key) { return this.settings[key]; }
    setSetting(key, value) {
      this.settings[key] = value;
      Adapter.saveJSON("settings", this.settings);
    }

    // --------------------------------------------------------- 历史
    addHistory(entry) {
      this.history.unshift(Object.assign({ time: new Date().toISOString() }, entry));
      if (this.history.length > 200) this.history.pop();
      Adapter.saveJSON("history", this.history);
    }
    clearHistory() { this.history = []; Adapter.saveJSON("history", []); }

    // --------------------------------------------------------- 日志
    addLog(level, message) {
      const lv = LOG_LEVELS.includes(level) ? level : "INFO";
      this.logs.push({ time: new Date().toLocaleTimeString(), level: lv, message });
      if (this.logs.length > 500) this.logs.shift();
      Adapter.hostLog(lv, message);
    }
    filteredLogs(level) {
      const idx = LOG_LEVELS.indexOf(level);
      return this.logs.filter((l) => LOG_LEVELS.indexOf(l.level) >= idx);
    }
    clearLogs() { this.logs = []; }

    // --------------------------------------------------------- 模板
    getPresets() { return PRESETS; }

    setStatus(status, detail) {
      this.status = status;
      this.statusDetail = detail || "";
    }
  }

  global.DSHStore = Store;
})(window);
