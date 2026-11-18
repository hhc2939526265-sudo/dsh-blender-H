/*
 * DSH 插件入口与生命周期。
 * manifest.json 中声明的 onEnable / onDisable / onUninstall 由宿主在对应时机调用。
 */
(function (global) {
  "use strict";

  let app = null;

  function boot() {
    const store = new global.DSHStore();
    const client = new global.DSHBridgeClient(store);
    const transfer = new global.DSHTransfer(client, store);
    const ui = new global.DSHUI({ store, client, transfer });
    app = { store, client, transfer, ui };
    ui.init();
    store.addLog("INFO", "DSH Blender Bridge 面板已加载");
    return app;
  }

  function onEnable() {
    if (!app) boot();
    const host = app.store.getSetting("host");
    const port = app.store.getSetting("port");
    app.client.connect(host, port);
  }

  function onDisable() {
    if (app) app.client.disconnect();
  }

  function onUninstall() {
    if (app) app.client.disconnect();
    global.localStorage.removeItem("dsh_bridge_history");
  }

  // 独立浏览器调试场景：DOM 就绪后自动 boot（宿主环境由 onEnable 触发）
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  global.main = { onEnable, onDisable, onUninstall };
})(window);
