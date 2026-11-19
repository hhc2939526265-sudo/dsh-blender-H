/*
 * DSH 插件入口与生命周期。
 * manifest.json 中声明的 onEnable / onDisable / onUninstall 由宿主在对应时机调用。
 */
(function (global) {
  "use strict";

  let app = null;

  function boot() {
    // 宿主重复回调 onEnable / 调试场景重复触发 DOMContentLoaded 时，只初始化一次，
    // 避免重复绑定按钮事件、重复创建 WebSocket 导致一次操作被执行多次。
    if (app) return app;
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
