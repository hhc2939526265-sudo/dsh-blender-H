/*
 * WebSocket 桥接客户端（DSH 端）。
 *
 * 能力：
 * - 本地长连接，应用层心跳（30s），超时判定断线
 * - 断线自动重连，指数退避（1s → 2s → 4s … 上限 30s）
 * - 指令 Promise 化：cmd_id 关联回执，超时自动 reject
 * - 异步事件 / 分片传输消息通过事件总线分发给 UI 与传输层
 */
(function (global) {
  "use strict";

  const P = global.DSHProtocol;

  class BridgeClient {
    constructor(store) {
      this.store = store;
      this.ws = null;
      this.manualClose = false;
      this.pending = new Map(); // cmd_id -> { resolve, reject, timer }
      this.listeners = { status: [], event: [], transfer: [] };
      this.heartbeatTimer = null;
      this.reconnectTimer = null;
      this.backoff = 1;
      this.lastPong = Date.now();
      this.url = "";
      // 连接代际号：每次新建连接自增，旧实例的 onopen/onclose 回调直接丢弃，
      // 避免重连竞态下新旧两个 WebSocket 并存、旧连接关闭后又触发一次重连。
      this._gen = 0;
    }

    // ------------------------------------------------------- 连接
    connect(host, port) {
      this.manualClose = false;
      this.url = `ws://${host}:${port}`;
      // 先拆除上一条残留连接及其回调，防止重复建连与重复触发
      this._teardownExisting();
      this._open();
    }

    _teardownExisting() {
      if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
      this._stopHeartbeat();
      if (this.ws) {
        const old = this.ws;
        this.ws = null;
        try {
          old.onopen = null; old.onmessage = null;
          old.onerror = null; old.onclose = null;
          old.close();
        } catch (e) { /* ignore */ }
      }
    }

    _open() {
      this._emitStatus("connecting", `正在连接 ${this.url}`);
      const gen = ++this._gen;
      let sock;
      try {
        // 配置了共享口令时，通过 Sec-WebSocket-Protocol 子协议末段携带
        const token = this.store.getSetting("auth_token") || "";
        const protocols = token ? [`dsh-bridge,${token}`] : undefined;
        sock = new WebSocket(this.url, protocols);
      } catch (e) {
        this._emitStatus("error", `连接创建失败: ${e.message}`);
        if (gen === this._gen) this._scheduleReconnect();
        return;
      }
      this.ws = sock;

      sock.onopen = () => {
        if (gen !== this._gen) return; // 已被更新的连接取代
        this.backoff = 1;
        this.lastPong = Date.now();
        this._emitStatus("connected", "连接已建立，等待握手");
        // 握手，拉取服务端能力清单
        this.send("system.handshake", {})
          .then((res) => this._emitStatus("connected", `已握手，指令数 ${(res.commands || []).length}`))
          .catch(() => this._emitStatus("connected", "已连接（握手未应答）"));
        this._startHeartbeat();
      };

      sock.onmessage = (ev) => { if (gen === this._gen) this._onMessage(ev.data); };
      sock.onerror = () => { if (gen === this._gen) this._emitStatus("error", "WebSocket 错误"); };
      sock.onclose = () => {
        // 旧代际连接关闭：不更新状态、不调度重连，防止竞态重复建连
        if (gen !== this._gen) return;
        this.ws = null;
        this._stopHeartbeat();
        this._emitStatus("disconnected", "连接已断开");
        if (!this.manualClose) this._scheduleReconnect();
      };
    }

    disconnect() {
      this.manualClose = true;
      this._gen += 1; // 使现存回调全部失效
      this._teardownExisting();
      this._rejectAllPending("连接已断开");
    }

    _scheduleReconnect() {
      if (!this.store.getSetting("auto_reconnect")) return;
      if (this.reconnectTimer) return;
      const delay = Math.min(this.backoff, 30);
      this.backoff = Math.min(this.backoff * 2, 30);
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        this._open();
      }, delay * 1000);
    }

    // ------------------------------------------------------- 心跳
    _startHeartbeat() {
      this._stopHeartbeat();
      const interval = (this.store.getSetting("heartbeat_interval") || 30) * 1000;
      this.heartbeatTimer = setInterval(() => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        // 超时判定：距上次 pong 超过 间隔 + 10s 则主动重连
        if (Date.now() - this.lastPong > interval + 10000) {
          this._emitStatus("error", "心跳超时，准备重连");
          try { this.ws.close(); } catch (e) { /* ignore */ }
          return;
        }
        this.send("system.heartbeat", {}).catch(() => { /* 心跳失败忽略 */ });
      }, interval);
    }

    _stopHeartbeat() {
      if (this.heartbeatTimer) { clearInterval(this.heartbeatTimer); this.heartbeatTimer = null; }
    }

    // ------------------------------------------------------- 发送
    send(cmdType, payload, timeoutMs) {
      return new Promise((resolve, reject) => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
          reject(new Error("连接未打开")); return;
        }
        const envelope = P.newCommand(cmdType, payload);
        const timeout = timeoutMs || 120000;
        const timer = setTimeout(() => {
          this.pending.delete(envelope.cmd_id);
          reject(new Error(`指令超时: ${cmdType}`));
        }, timeout);
        this.pending.set(envelope.cmd_id, { resolve, reject, timer });
        this.ws.send(JSON.stringify(envelope));
      });
    }

    /** 不等待回执的单向事件推送（状态 / 进度类） */
    emit(cmdType, payload) {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      this.ws.send(JSON.stringify(P.newCommand(cmdType, payload)));
    }

    // ------------------------------------------------------- 收包
    _onMessage(raw) {
      let msg;
      try { msg = JSON.parse(raw); } catch (e) {
        this.store.addLog("ERROR", "收到非法 JSON 报文"); return;
      }
      const err = P.validateEnvelope(msg);
      if (err.code) { this.store.addLog("ERROR", err.message); return; }

      // 心跳回执
      if (msg.cmd_type === "system.heartbeat" || msg.cmd_type === "system.pong") {
        this.lastPong = Date.now(); return;
      }

      const waiter = this.pending.get(msg.cmd_id);
      if (waiter) {
        clearTimeout(waiter.timer);
        this.pending.delete(msg.cmd_id);
        if (msg.status === P.STATUS.SUCCESS) waiter.resolve(msg.result);
        else waiter.reject(new Error((msg.error && msg.error.message) || "指令执行失败"));
        return;
      }

      // 异步事件 / 传输消息
      if (msg.cmd_type && msg.cmd_type.startsWith("transfer.")) {
        this._emit("transfer", msg);
      } else {
        this._emit("event", msg);
      }
    }

    _rejectAllPending(reason) {
      this.pending.forEach((w) => { clearTimeout(w.timer); w.reject(new Error(reason)); });
      this.pending.clear();
    }

    // ------------------------------------------------------- 事件总线
    on(type, cb) { (this.listeners[type] || []).push(cb); }
    _emit(type, payload) {
      (this.listeners[type] || []).forEach((cb) => { try { cb(payload); } catch (e) { /* ignore */ } });
    }
    _emitStatus(status, detail) {
      this.store.setStatus(status, detail);
      this._emit("status", { status, detail });
    }

    get connected() { return this.ws && this.ws.readyState === WebSocket.OPEN; }
  }

  global.DSHBridgeClient = BridgeClient;
})(window);
