/*
 * DSH 面板 UI 绑定与渲染。
 * 负责：选项卡切换、上传拖拽、参数读写、动作触发、状态 / 日志 / 历史 / 预览渲染。
 */
(function (global) {
  "use strict";

  const $ = (id) => document.getElementById(id);

  class UI {
    constructor(app) {
      this.app = app;
      this.store = app.store;
      this.client = app.client;
      this.transfer = app.transfer;
      this.pendingImages = [];
      this.pendingVideo = [];
      this.addonCache = [];
      this.selectedModule = null;
    }

    init() {
      this._bindTabs();
      this._bindConnection();
      this._bindUploads();
      this._bindActions();
      this._bindSettingsInputs();
      this._renderPresets();
      this._renderHistory();
      this._renderLogs();
      this._bindClientEvents();
      this._syncSettingsToInputs();
    }

    // ------------------------------------------------------- 选项卡
    _bindTabs() {
      document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
          document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
          document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
          tab.classList.add("active");
          document.querySelector(`.tab-pane[data-pane="${tab.dataset.tab}"]`).classList.add("active");
          if (tab.dataset.tab === "addons") this._loadAddons();
        });
      });
    }

    switchTab(name) {
      document.querySelector(`.tab[data-tab="${name}"]`)?.click();
    }

    // ------------------------------------------------------- 连接
    _bindConnection() {
      $("btn-connect").addEventListener("click", () => {
        const host = $("cfg-host").value.trim();
        const port = parseInt($("cfg-port").value, 10) || 8765;
        this.store.setSetting("host", host);
        this.store.setSetting("port", port);
        this.client.connect(host, port);
      });
      $("btn-disconnect").addEventListener("click", () => this.client.disconnect());
      $("btn-scan-blender").addEventListener("click", () => this._scanBlender());
    }

    _scanBlender() {
      const candidates = global.DSHAdapter.listBlenderCandidates();
      const list = $("blender-candidates");
      list.innerHTML = "";
      candidates.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p; list.appendChild(opt);
      });
      const input = $("cfg-blender-path");
      if (!input.value && candidates.length) input.value = candidates[0];
      this.store.addLog("INFO", `扫描到 ${candidates.length} 个候选 Blender 路径`);
    }

    _bindClientEvents() {
      this.client.on("status", (s) => this._renderStatus(s));
      this.client.on("event", (msg) => this._onEvent(msg));
      global.addEventListener("dsh:preview", (e) => this._onPreview(e.detail));
    }

    _renderStatus(s) {
      const dot = $("status-dot");
      const text = $("status-text");
      dot.className = "brand-dot" + (s.status === "connected" ? " online" : s.status === "error" ? " offline" : "");
      text.textContent = `${s.status} · ${s.detail || ""}`;
    }

    _onEvent(msg) {
      const result = msg.result || {};
      if (msg.cmd_type === "system.status") {
        $("stat-pending").textContent = `排队 ${result.pending || 0}`;
        $("stat-success").textContent = `成功 ${(result.stats || {}).success || 0}`;
        $("stat-failed").textContent = `失败 ${(result.stats || {}).failed || 0}`;
        this.store.provider = result.provider || "-";
        $("stat-provider").textContent = `AI 后端: ${this.store.provider}`;
      } else if (msg.cmd_type === "render.progress") {
        this.store.addLog("INFO", `渲染进度: ${result.stage}`);
      }
    }

    // ------------------------------------------------------- 上传
    _bindUploads() {
      const imageZone = $("image-dropzone");
      const videoZone = $("video-dropzone");

      imageZone.addEventListener("click", () => $("file-input-image").click());
      videoZone.addEventListener("click", () => $("file-input-video").click());
      $("file-input-image").addEventListener("change", (e) => {
        this._addFiles(Array.from(e.target.files), "image"); e.target.value = "";
      });
      $("file-input-video").addEventListener("change", (e) => {
        this._addFiles(Array.from(e.target.files), "video"); e.target.value = "";
      });

      [imageZone, videoZone].forEach((zone) => {
        zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
        zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
        zone.addEventListener("drop", (e) => {
          e.preventDefault(); zone.classList.remove("dragover");
          const kind = zone.dataset.kind;
          this._addFiles(Array.from(e.dataTransfer.files), kind);
        });
      });
    }

    _addFiles(files, kind) {
      const list = kind === "image" ? this.pendingImages : this.pendingVideo;
      files.forEach((file) => {
        if (kind === "image" && !/image\/(jpeg|png|webp)/.test(file.type)) return;
        if (kind === "video" && !/video\//.test(file.type)) return;
        list.push(file);
      });
      this._renderPreviews(kind);
    }

    _renderPreviews(kind) {
      const list = kind === "image" ? this.pendingImages : this.pendingVideo;
      const box = $(kind === "image" ? "image-preview-list" : "video-preview-list");
      box.innerHTML = "";
      list.forEach((file, idx) => {
        const item = document.createElement("div");
        item.className = "preview-item";
        const url = URL.createObjectURL(file);
        const media = kind === "image"
          ? `<img src="${url}" alt="${file.name}" />`
          : `<video src="${url}" muted />`;
        item.innerHTML = `${media}<button class="remove" title="移除">×</button>`;
        item.querySelector(".remove").addEventListener("click", () => {
          list.splice(idx, 1); this._renderPreviews(kind);
        });
        box.appendChild(item);
      });
    }

    // ------------------------------------------------------- 动作
    _bindActions() {
      $("btn-build-character").addEventListener("click", () => this._buildCharacter());
      $("btn-mocap").addEventListener("click", () => this._videoPipeline());
      $("btn-nl-dispatch").addEventListener("click", () => this._nlDispatch());
      $("btn-nl-example").addEventListener("click", () => {
        $("nl-prompt").value = "在场景中央生成一个倒角立方体，阵列 3 个，金属材质，绕 Z 轴旋转一周";
      });
      $("btn-render").addEventListener("click", () => this._render());
      $("btn-export-asset").addEventListener("click", () => this._iterate());
      $("btn-pause").addEventListener("click", () => this.store.addLog("WARNING", "队列暂停开关：当前为本地状态提示"));
      $("btn-stop").addEventListener("click", () => {
        this.client.emit("system.stop", {});
        this.store.addLog("WARNING", "已向 Blender 发送停止指令");
      });
      $("btn-addon-refresh").addEventListener("click", () => this._loadAddons());
      $("btn-addon-match").addEventListener("click", () => this._matchAddons());
      $("btn-addon-invoke").addEventListener("click", () => this._invokeOperator());
      $("btn-export-log").addEventListener("click", () => this._exportLog());
      $("btn-clear-log").addEventListener("click", () => { this.store.clearLogs(); this._renderLogs(); });
      $("log-filter").addEventListener("change", () => this._renderLogs());
    }

    async _buildCharacter() {
      if (!this._ensureConnected()) return;
      if (!this.pendingImages.length) { this.store.addLog("WARNING", "请先上传人物图片"); return; }
      const btn = $("btn-build-character"); btn.disabled = true;
      try {
        const paths = [];
        for (const file of this.pendingImages) {
          const up = await this.transfer.uploadFile(file);
          paths.push(up.path);
        }
        const res = await this.client.send("pipeline.character", {
          image_paths: paths, quality: this.store.getSetting("mesh_quality"),
        });
        this._recordHistory("pipeline.character", res);
        $("character-meta").textContent = JSON.stringify(res, null, 2);
        this.store.addLog("INFO", `角色生成完成: ${res.body || ""}`);
      } catch (e) {
        this._recordHistory("pipeline.character", { error: e.message }, "FAILED");
        this.store.addLog("ERROR", `角色生成失败: ${e.message}`);
      } finally { btn.disabled = false; }
    }

    async _videoPipeline() {
      if (!this._ensureConnected()) return;
      if (!this.pendingVideo.length) { this.store.addLog("WARNING", "请先上传参考视频"); return; }
      const btn = $("btn-mocap"); btn.disabled = true;
      try {
        const up = await this.transfer.uploadFile(this.pendingVideo[0]);
        const res = await this.client.send("pipeline.video", {
          video_path: up.path,
          kind: $("motion-kind").value,
          confidence: parseFloat($("cfg-confidence").value),
          effect_strength: parseFloat($("cfg-effect").value),
        });
        this._recordHistory("pipeline.video", res);
        $("motion-meta").textContent = JSON.stringify(res, null, 2);
        this.store.addLog("INFO", "视频解析与复刻完成");
      } catch (e) {
        this._recordHistory("pipeline.video", { error: e.message }, "FAILED");
        this.store.addLog("ERROR", `视频复刻失败: ${e.message}`);
      } finally { btn.disabled = false; }
    }

    async _nlDispatch() {
      if (!this._ensureConnected()) return;
      const prompt = $("nl-prompt").value.trim();
      if (!prompt) { this.store.addLog("WARNING", "请输入提示词"); return; }
      try {
        const res = await this.client.send("nl.dispatch", {
          prompt: prompt, dry_run: $("nl-dryrun").checked,
        });
        $("nl-result").textContent = JSON.stringify(res, null, 2);
        this._recordHistory("nl.dispatch", res);
      } catch (e) {
        this._recordHistory("nl.dispatch", { error: e.message }, "FAILED");
        $("nl-result").textContent = `错误: ${e.message}`;
        this.store.addLog("ERROR", e.message);
      }
    }

    async _render() {
      if (!this._ensureConnected()) return;
      try {
        await this.client.send("render.switch_engine", { engine: $("cfg-engine").value });
        await this.client.send("render.settings", {
          resolution: [parseInt($("cfg-res-x").value, 10), parseInt($("cfg-res-y").value, 10)],
          samples: parseInt($("cfg-samples").value, 10),
        });
        const res = await this.client.send("render.execute", { animation: false });
        $("render-meta").textContent = JSON.stringify(res, null, 2);
        this._recordHistory("render.execute", res);
      } catch (e) {
        this._recordHistory("render.execute", { error: e.message }, "FAILED");
        this.store.addLog("ERROR", `渲染失败: ${e.message}`);
      }
    }

    async _iterate() {
      if (!this._ensureConnected()) return;
      try {
        const res = await this.client.send("pipeline.iterate", {
          iteration: (this.store.history.filter((h) => h.cmd === "pipeline.iterate").length) + 1,
        });
        this._recordHistory("pipeline.iterate", res);
        this.store.addLog("INFO", "资产已回传，可在 DSH 端继续 AI 优化");
      } catch (e) {
        this._recordHistory("pipeline.iterate", { error: e.message }, "FAILED");
        this.store.addLog("ERROR", `回传失败: ${e.message}`);
      }
    }

    // ------------------------------------------------------- 插件生态
    async _loadAddons() {
      if (!this._ensureConnected()) return;
      try {
        const res = await this.client.send("addon.list", {});
        this.addonCache = res.addons || [];
        this._renderAddonList();
        this.store.addLog("INFO", `识别到 ${this.addonCache.length} 个已启用第三方插件`);
      } catch (e) {
        this.store.addLog("ERROR", `插件列表获取失败: ${e.message}`);
      }
    }

    _renderAddonList() {
      const box = $("addon-list");
      box.innerHTML = "";
      if (!this.addonCache.length) {
        box.innerHTML = '<div class="placeholder">未检测到第三方插件（需先在 Blender 偏好设置中启用）</div>';
        return;
      }
      this.addonCache.forEach((addon) => {
        const card = document.createElement("div");
        card.className = "addon-card" + (addon.module === this.selectedModule ? " active" : "");
        card.innerHTML = `<div class="name">${this._esc(addon.name)}</div>
          <div class="desc">${this._esc(addon.description || "—")}</div>
          <div class="meta">
            <span class="tag">${this._esc(addon.capability)}</span>
            <span class="placeholder">${addon.version ? "v" + this._esc(addon.version) : ""} · ${addon.operator_count} 个算子</span>
          </div>`;
        card.addEventListener("click", () => this._selectAddon(addon.module));
        box.appendChild(card);
      });
    }

    async _selectAddon(module) {
      if (!this._ensureConnected()) return;
      this.selectedModule = module;
      this._renderAddonList();
      try {
        const detail = await this.client.send("addon.detail", { module });
        this._renderDetail(detail);
      } catch (e) {
        this.store.addLog("ERROR", `插件详情获取失败: ${e.message}`);
      }
    }

    _renderDetail(detail) {
      $("addon-detail-meta").textContent =
        `${detail.name} · ${detail.author || ""} ${detail.version ? "v" + detail.version : ""}\n` +
        `分类: ${detail.category || "-"} · 能力: ${detail.capability}\n${detail.description || ""}`;
      const opBox = $("addon-operator-list");
      opBox.innerHTML = "";
      const datalist = $("addon-op-candidates");
      datalist.innerHTML = "";
      const ops = detail.operators || [];
      if (!ops.length) {
        opBox.innerHTML = '<div class="placeholder">该插件暂无可暴露的算子</div>';
        return;
      }
      ops.forEach((op) => {
        const opt = document.createElement("option");
        opt.value = op.idname;
        datalist.appendChild(opt);
        const props = (op.properties || [])
          .map((p) => `${p.name}${p.required ? "*" : ""}:${p.type}`).join(", ");
        const item = document.createElement("div");
        item.className = "op-item";
        item.innerHTML = `<div class="op-title"><span>${this._esc(op.label)}</span><span class="op-id">${this._esc(op.idname)}</span></div>
          <div class="op-props">${props || "无参数"}</div>`;
        item.addEventListener("click", () => {
          $("addon-op-id").value = op.idname;
          $("addon-invoke-result").textContent = `已选中算子 ${op.idname}，可补充参数后调用`;
        });
        opBox.appendChild(item);
      });
    }

    async _matchAddons() {
      if (!this._ensureConnected()) return;
      const intent = $("addon-match-prompt").value.trim();
      if (!intent) { this.store.addLog("WARNING", "请输入要匹配的意图"); return; }
      try {
        const res = await this.client.send("addon.match", { intent, top_n: 5 });
        const box = $("addon-match-list");
        box.innerHTML = "";
        if (!res.matches || !res.matches.length) {
          box.innerHTML = '<div class="placeholder">未匹配到相关插件</div>';
          return;
        }
        res.matches.forEach((m) => {
          const card = document.createElement("div");
          card.className = "addon-card";
          card.innerHTML = `<div class="name">${this._esc(m.name)}</div>
            <div class="desc">${this._esc(m.description || "—")}</div>
            <div class="meta"><span class="tag">${this._esc(m.capability)}</span>
            <span class="placeholder">命中 ${m.score} 词 · ${(m.matched || []).join("/")}</span></div>`;
          card.addEventListener("click", () => this._selectAddon(m.module));
          box.appendChild(card);
        });
      } catch (e) {
        this.store.addLog("ERROR", `插件匹配失败: ${e.message}`);
      }
    }

    async _invokeOperator() {
      if (!this._ensureConnected()) return;
      const operator = $("addon-op-id").value.trim();
      if (!operator) { this.store.addLog("WARNING", "请先选择或填写算子 ID"); return; }
      let params = {};
      const raw = $("addon-op-params").value.trim();
      if (raw) {
        try { params = JSON.parse(raw); }
        catch (e) { this.store.addLog("ERROR", "参数 JSON 解析失败: " + e.message); return; }
      }
      const mode = $("addon-op-mode").value;
      try {
        const res = await this.client.send("addon.invoke", { operator, params, mode });
        $("addon-invoke-result").textContent = JSON.stringify(res, null, 2);
        this._recordHistory("addon.invoke", res);
        this.store.addLog("INFO", `算子调用成功: ${operator}`);
      } catch (e) {
        this._recordHistory("addon.invoke", { error: e.message }, "FAILED");
        $("addon-invoke-result").textContent = `错误: ${e.message}`;
        this.store.addLog("ERROR", `算子调用失败: ${e.message}`);
      }
    }

    _esc(text) {
      return String(text == null ? "" : text).replace(/[&<>"']/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    _ensureConnected() {
      if (!this.client.connected) {
        this.store.addLog("WARNING", "请先连接 Blender 桥接服务");
        return false;
      }
      return true;
    }

    // ------------------------------------------------------- 预览
    _onPreview(detail) {
      if (!detail) return;
      const safeName = this._esc(detail.filename || "");
      const isVideo = /\.(mp4|webm|mov)$/i.test(detail.filename || "");
      const html = isVideo
        ? `<video src="${detail.url}" controls autoplay loop />`
        : `<img src="${detail.url}" alt="${safeName}" />`;
      const stage = $("render-preview");
      if (stage) stage.innerHTML = html;
      // 同时回填到当前激活页签的预览区
      const active = document.querySelector(".tab-pane.active .preview-stage");
      if (active && active !== stage) active.innerHTML = html;
    }

    // ------------------------------------------------------- 历史 / 预设
    _recordHistory(cmd, result, status) {
      this.store.addHistory({ cmd, status: status || "SUCCESS", result });
      this._renderHistory();
    }

    _renderHistory() {
      const box = $("history-list");
      box.innerHTML = "";
      if (!this.store.history.length) { box.innerHTML = '<div class="placeholder">暂无执行历史</div>'; return; }
      this.store.history.forEach((h) => {
        const item = document.createElement("div");
        item.className = "history-item";
        const cmd = this._esc(h.cmd);
        const status = this._esc(h.status);
        item.innerHTML = `<span class="cmd">${cmd}</span>
          <span class="status-${status}">${status}</span>
          <span>${new Date(h.time).toLocaleTimeString()}</span>`;
        box.appendChild(item);
      });
    }

    _renderPresets() {
      const box = $("preset-list");
      box.innerHTML = "";
      this.store.getPresets().forEach((preset) => {
        const card = document.createElement("div");
        card.className = "preset-card";
        card.innerHTML = `<div class="name">${preset.name}</div><div class="desc">${preset.desc}</div>`;
        card.addEventListener("click", () => this._applyPreset(preset));
        box.appendChild(card);
      });
    }

    _applyPreset(preset) {
      this.switchTab(preset.tab);
      if (preset.payload.quality) $("cfg-quality").value = preset.payload.quality;
      if (preset.payload.cycle) $("motion-kind").value = preset.payload.kind === "mocap" ? "mocap" : "both";
      if (preset.payload.action === "export") this._iterate();
      this.store.addLog("INFO", `已套用模板: ${preset.name}`);
    }

    // ------------------------------------------------------- 日志
    _renderLogs() {
      const level = $("log-filter").value;
      const box = $("log-panel");
      const logs = this.store.filteredLogs(level);
      box.innerHTML = logs.map((l) =>
        `<div class="log-line log-${l.level}">${l.time} | ${l.level} | ${l.message}</div>`
      ).join("");
      box.scrollTop = box.scrollHeight;
    }

    _exportLog() {
      const text = this.store.logs.map((l) => `${l.time} | ${l.level} | ${l.message}`).join("\n");
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `dsh_bridge_${Date.now()}.log`;
      a.click();
    }

    // ------------------------------------------------------- 设置同步
    _bindSettingsInputs() {
      const map = [
        ["cfg-blender-path", "blender_path"],
        ["cfg-host", "host"], ["cfg-port", "port"], ["cfg-quality", "mesh_quality"],
        ["cfg-confidence", "mocap_confidence"], ["cfg-effect", "effect_strength"],
        ["cfg-engine", "render_engine"], ["cfg-samples", "render_samples"],
      ];
      map.forEach(([id, key]) => {
        $(id).addEventListener("change", (e) => {
          let v = e.target.value;
          if (["port", "render_samples"].includes(key)) v = parseInt(v, 10);
          if (["mocap_confidence", "effect_strength"].includes(key)) v = parseFloat(v);
          this.store.setSetting(key, v);
        });
      });
    }

    _syncSettingsToInputs() {
      $("cfg-blender-path").value = this.store.getSetting("blender_path") || "";
      $("cfg-host").value = this.store.getSetting("host");
      $("cfg-port").value = this.store.getSetting("port");
      $("cfg-quality").value = this.store.getSetting("mesh_quality");
      $("cfg-confidence").value = this.store.getSetting("mocap_confidence");
      $("cfg-effect").value = this.store.getSetting("effect_strength");
      $("cfg-engine").value = this.store.getSetting("render_engine");
      $("cfg-samples").value = this.store.getSetting("render_samples");
    }
  }

  global.DSHUI = UI;
})(window);
