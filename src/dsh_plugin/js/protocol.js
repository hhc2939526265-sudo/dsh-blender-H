/*
 * 标准化 JSON 通信协议（DSH 端）。
 * 与 Blender 端 protocol.py 保持完全一致的 6 字段信封：
 * cmd_id / cmd_type / payload / status / result / error
 */
(function (global) {
  "use strict";

  const STATUS = {
    PENDING: "PENDING", RUNNING: "RUNNING", SUCCESS: "SUCCESS",
    FAILED: "FAILED", CANCELED: "CANCELED",
  };

  const REQUIRED_FIELDS = ["cmd_id", "cmd_type", "payload", "status", "result", "error"];

  function uuid() {
    if (global.crypto && global.crypto.randomUUID) return global.crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  /** 构造出站指令信封 */
  function newCommand(cmdType, payload, cmdId) {
    return {
      cmd_id: cmdId || uuid(),
      cmd_type: cmdType,
      payload: payload || {},
      status: STATUS.PENDING,
      result: {},
      error: { code: "", message: "", detail: "" },
    };
  }

  /** 校验入站信封，返回错误描述（空对象表示通过） */
  function validateEnvelope(msg) {
    if (typeof msg !== "object" || msg === null) {
      return { code: "E_PROTOCOL", message: "消息体必须为 JSON 对象" };
    }
    const missing = REQUIRED_FIELDS.filter((f) => !(f in msg));
    if (missing.length) {
      return { code: "E_PROTOCOL", message: `缺少必填字段: ${missing.join(", ")}` };
    }
    if (typeof msg.cmd_id !== "string" || !msg.cmd_id) {
      return { code: "E_PROTOCOL", message: "cmd_id 非法" };
    }
    if (typeof msg.cmd_type !== "string" || !msg.cmd_type) {
      return { code: "E_PROTOCOL", message: "cmd_type 非法" };
    }
    if (typeof msg.payload !== "object" || msg.payload === null) {
      return { code: "E_PROTOCOL", message: "payload 必须为对象" };
    }
    return {};
  }

  global.DSHProtocol = { STATUS, REQUIRED_FIELDS, uuid, newCommand, validateEnvelope };
})(window);
