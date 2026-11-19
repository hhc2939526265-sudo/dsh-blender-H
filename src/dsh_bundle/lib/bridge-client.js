/**
 * dsh-blender-bridge · 最小 WebSocket 客户端
 *
 * 对接 Blender 端插件（DSH Blender Bridge）的本地协议：
 *   ws://127.0.0.1:8765
 *   请求帧  { cmd_id, cmd_type, payload: {...}, status: "PENDING", result: null, error: null }
 *   响应帧  { cmd_id, cmd_type, payload, status: "SUCCESS" | "FAILED", result | error }
 *
 * 注意：服务端（core/bridge.py `_on_ws_message` + `protocol.validate_envelope`）
 * 强校验帧结构，缺 result / error 会直接回 E_PROTOCOL；
 * 连上后服务端还会主动推一帧 cmd_id 为空的 system.status，只当状态缓存、不参与匹配；
 * system.status / system.heartbeat 之外的指令都排队到主线程（0.1s 节拍）执行。
 *
 * 只用 Node 22+ 自带的全局 WebSocket，不引入任何依赖。
 */

const DEFAULTS = {
  url: 'ws://127.0.0.1:8765',
  connectTimeoutMs: 5000,
  requestTimeoutMs: 120000,
};

let seq = 0;

export class BlenderBridgeClient {
  constructor(options = {}) {
    this.url = options.url || DEFAULTS.url;
    // 插件端 config.auth_token 非空时，口令走 Sec-WebSocket-Protocol 尾段传给服务端
    this.token = typeof options.token === 'string' ? options.token.trim() : '';
    this.connectTimeoutMs = options.connectTimeoutMs || DEFAULTS.connectTimeoutMs;
    this.requestTimeoutMs = options.requestTimeoutMs || DEFAULTS.requestTimeoutMs;
    this.ws = null;
    this.opening = null;
    this.pending = new Map();
    this.lastError = '';
    this.lastPush = null;
  }

  get connected() {
    return Boolean(this.ws) && this.ws.readyState === 1; // OPEN
  }

  /** 建立（或复用）连接；失败时抛出带排查提示的错误。 */
  connect() {
    if (this.connected) return Promise.resolve();
    if (this.opening) return this.opening;
    this.opening = new Promise((resolve, reject) => {
      let settled = false;
      const done = (err) => {
        if (settled) return;
        settled = true;
        this.opening = null;
        if (err) reject(err);
        else resolve();
      };
      let ws;
      try {
        ws = this.token
          ? new WebSocket(this.url, ['dsh-bridge', this.token])
          : new WebSocket(this.url);
      } catch (error) {
        done(new Error(this.hint(error && error.message)));
        return;
      }
      const timer = setTimeout(() => {
        try { ws.close(); } catch { /* ignore */ }
        done(new Error(this.hint('连接超时')));
      }, this.connectTimeoutMs);

      ws.addEventListener('open', () => {
        clearTimeout(timer);
        this.ws = ws;
        this.lastError = '';
        done();
      });
      ws.addEventListener('message', (event) => this._onMessage(event.data));
      ws.addEventListener('error', () => {
        clearTimeout(timer);
        done(new Error(this.hint(this.lastError || '连接被拒绝')));
      });
      ws.addEventListener('close', () => {
        clearTimeout(timer);
        if (this.ws === ws) this.ws = null;
        for (const [, entry] of this.pending) {
          clearTimeout(entry.timer);
          entry.reject(new Error(this.hint('连接已断开')));
        }
        this.pending.clear();
        done(new Error(this.hint('连接已断开')));
      });
    });
    return this.opening;
  }

  hint(detail) {
    return '无法连接 Blender 桥接端口 ' + this.url + '（' + detail + '）。' +
      '请检查：1) Blender 正在运行；2) 在 3D 视图按 N 打开侧栏 → DSH Bridge 面板 → 点「启动服务」；' +
      '3) 端口 8765 没被别的程序占用。';
  }

  _onMessage(raw) {
    let msg;
    try {
      msg = JSON.parse(typeof raw === 'string' ? raw : String(raw));
    } catch {
      return;
    }
    if (!msg || !msg.cmd_id) {
      // 服务端主动推送（hello / 连接数变化）：缓存下来给 status() 用
      if (msg && msg.cmd_type === 'system.status' && msg.result) this.lastPush = msg.result;
      return;
    }
    const entry = this.pending.get(msg.cmd_id);
    if (!entry) return;
    clearTimeout(entry.timer);
    this.pending.delete(msg.cmd_id);
    entry.resolve(msg);
  }

  /** 发送一条指令并等待同 cmd_id 的响应帧。 */
  async request(cmdType, payload = {}, timeoutMs = this.requestTimeoutMs) {
    await this.connect();
    const cmdId = 'dsh-' + process.pid + '-' + (++seq);
    // 服务端强校验帧结构：result / error 必须存在（可为 null），否则回 E_PROTOCOL。
    const frame = {
      cmd_id: cmdId,
      cmd_type: cmdType,
      payload: payload || {},
      status: 'PENDING',
      result: null,
      error: null,
    };
    const response = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(cmdId);
        reject(new Error('Blender 指令超时（' + Math.round(timeoutMs / 1000) + 's）：' + cmdType));
      }, timeoutMs);
      this.pending.set(cmdId, { resolve, reject, timer });
    });
    try {
      this.ws.send(JSON.stringify(frame));
    } catch (error) {
      const entry = this.pending.get(cmdId);
      if (entry) {
        clearTimeout(entry.timer);
        this.pending.delete(cmdId);
      }
      throw new Error(this.hint(error && error.message));
    }
    return response;
  }

  /**
   * 便捷方法：读桥接状态。
   * `system.status` 只由服务端主动推送、不可当作指令发送，所以这里用握手指令
   * （`system.handshake` → `{server, version, commands}`）确认链路，再拼上 hello 里的连接数。
   */
  async status(timeoutMs = 8000) {
    const res = await this.request('system.handshake', {}, timeoutMs);
    if (res.status !== 'SUCCESS') {
      throw new Error('读取状态失败：' + JSON.stringify(res.error || res.result || res));
    }
    const result = res.result || {};
    return {
      running: true,
      server: result.server,
      version: result.version,
      commands: Array.isArray(result.commands) ? result.commands : [],
      connections: this.lastPush && this.lastPush.connections != null ? this.lastPush.connections : null,
      detail: this.lastPush && this.lastPush.detail ? this.lastPush.detail : '',
      url: this.url,
    };
  }

  close() {
    const ws = this.ws;
    this.ws = null;
    // 主动关闭时也要清掉在途请求，否则计时器最长会挂满 requestTimeoutMs
    for (const [, entry] of this.pending) {
      clearTimeout(entry.timer);
      entry.reject(new Error('连接已关闭'));
    }
    this.pending.clear();
    if (ws) {
      try { ws.close(); } catch { /* ignore */ }
    }
  }
}

export default BlenderBridgeClient;
