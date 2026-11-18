/*
 * DSH 宿主运行时适配层。
 *
 * DSH 宿主在加载插件时会注入全局 ``window.DSH`` 能力对象（配置读写 / 日志 /
 * 文件对话框等）。本模块统一封装调用：宿主可用时走宿主 API，不可用时（独立
 * 浏览器调试场景）自动降级到 localStorage，保证面板可独立运行。
 */
(function (global) {
  "use strict";

  const host = global.DSH || null;
  const hasHost = !!(host && typeof host === "object");

  function readConfig(key, fallback) {
    try {
      if (hasHost && typeof host.getConfig === "function") {
        const v = host.getConfig(key);
        return v === undefined || v === null ? fallback : v;
      }
      const raw = global.localStorage.getItem("dsh_bridge_cfg_" + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function writeConfig(key, value) {
    try {
      if (hasHost && typeof host.setConfig === "function") {
        host.setConfig(key, value);
        return;
      }
      global.localStorage.setItem("dsh_bridge_cfg_" + key, JSON.stringify(value));
    } catch (e) { /* 存储不可用时静默忽略 */ }
  }

  function hostLog(level, message) {
    try {
      if (hasHost && typeof host.log === "function") host.log(level, message);
    } catch (e) { /* ignore */ }
    // 同时落到浏览器控制台，便于调试
    const fn = console[level.toLowerCase()] || console.log;
    fn(`[${level}] ${message}`);
  }

  function loadJSON(key, fallback) {
    try {
      const raw = global.localStorage.getItem("dsh_bridge_" + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (e) { return fallback; }
  }

  function saveJSON(key, value) {
    try {
      global.localStorage.setItem("dsh_bridge_" + key, JSON.stringify(value));
    } catch (e) { /* ignore */ }
  }

  // 常见 Blender 安装候选路径（按平台分组）
  const CANDIDATES = {
    windows: [
      "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe",
      "C:/Program Files/Blender Foundation/Blender 4.3/blender.exe",
      "C:/Program Files/Blender Foundation/Blender 5.0/blender.exe",
      "C:/Program Files/Blender Foundation/Blender 5.3/blender.exe",
    ],
    macos: ["/Applications/Blender.app/Contents/MacOS/Blender"],
    linux: ["/usr/bin/blender", "/usr/local/bin/blender", "/opt/blender/blender"],
  };

  function listBlenderCandidates() {
    // 宿主提供扫描结果时优先使用；否则返回静态候选清单
    if (hasHost && typeof host.scanBlender === "function") {
      try { return host.scanBlender() || []; } catch (e) { /* fallback */ }
    }
    const plat = (navigator.platform || "").toLowerCase();
    const key = plat.indexOf("win") >= 0 ? "windows" : plat.indexOf("mac") >= 0 ? "macos" : "linux";
    return CANDIDATES[key] || CANDIDATES.linux;
  }

  global.DSHAdapter = {
    hasHost,
    readConfig, writeConfig, hostLog, loadJSON, saveJSON, listBlenderCandidates,
  };
})(window);
