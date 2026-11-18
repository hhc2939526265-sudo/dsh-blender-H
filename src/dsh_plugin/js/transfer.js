/*
 * 多模态文件分片传输（DSH 端）。
 *
 * 上行（DSH → Blender）：
 * - 读取文件为 ArrayBuffer，计算 MD5，按 64KB 分片 base64 编码
 * - begin 登记会话，依据回执的 missing 索引仅补发缺失分片（断点续传）
 * - end 合并并 MD5 校验
 *
 * 下行（Blender → DSH）：
 * - 监听 transfer.begin / chunk / end 事件，重组为 Blob，生成预览 ObjectURL
 */
(function (global) {
  "use strict";

  const CHUNK_SIZE = 64 * 1024;

  function arrayBufferToBase64(buffer) {
    let binary = "";
    const bytes = new Uint8Array(buffer);
    const block = 0x8000;
    for (let i = 0; i < bytes.length; i += block) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + block));
    }
    return btoa(binary);
  }

  class TransferClient {
    constructor(client, store) {
      this.client = client;
      this.store = store;
      this.inbound = new Map(); // file_id -> { filename, md5, chunk_count, chunks: {} }
      this.previewUrls = [];
      client.on("transfer", (msg) => this._onTransfer(msg));
    }

    // ------------------------------------------------------- 上行
    async uploadFile(file) {
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      const md5 = global.DSHMD5.hex(bytes);
      const chunkCount = Math.max(1, Math.ceil(bytes.length / CHUNK_SIZE));
      const fileId = md5.slice(0, 12) + "_" + Date.now().toString(36);

      // 切片
      const chunks = [];
      for (let i = 0; i < chunkCount; i++) {
        const start = i * CHUNK_SIZE;
        chunks.push(arrayBufferToBase64(bytes.subarray(start, start + CHUNK_SIZE)));
      }

      // begin（断点续传：拿回缺失分片索引）
      const beginRes = await this.client.send("transfer.begin", {
        file_id: fileId, filename: file.name, total_size: bytes.length,
        md5: md5, chunk_count: chunkCount,
      });
      const missing = (beginRes.missing || []).slice();

      // 仅补发缺失分片
      for (const index of missing) {
        await this.client.send("transfer.chunk", {
          file_id: fileId, index: index, data: chunks[index],
        });
      }

      // end + 校验
      const endRes = await this.client.send("transfer.end", { file_id: fileId });
      if (!endRes.ok) throw new Error(endRes.error || "文件传输校验失败");
      this.store.addLog("INFO", `文件上传完成: ${file.name} (${endRes.size} 字节)`);
      return { file_id: fileId, path: endRes.path, filename: file.name,
               size: endRes.size, md5: endRes.md5 };
    }

    // ------------------------------------------------------- 下行重组
    _onTransfer(msg) {
      const type = msg.cmd_type;
      const result = msg.result || {};
      if (type === "transfer.begin") {
        this.inbound.set(result.file_id, {
          filename: result.filename, md5: result.md5,
          chunk_count: result.chunk_count, chunks: {}, meta: result.meta || {},
        });
      } else if (type === "transfer.chunk") {
        const session = this.inbound.get(result.file_id);
        if (!session) return;
        session.chunks[result.index] = result.data;
      } else if (type === "transfer.end") {
        const session = this.inbound.get(result.file_id);
        if (!session) return;
        this.inbound.delete(result.file_id);
        this._assemble(session, result);
      }
    }

    _assemble(session, endResult) {
      const decoded = Object.keys(session.chunks)
        .sort((a, b) => a - b)
        .map((k) => atob(session.chunks[k]));
      const binary = decoded.join("");
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes]);
      const url = URL.createObjectURL(blob);
      this.previewUrls.push(url);
      this.store.previews[endResult.file_id] = { url, filename: session.filename, meta: session.meta };
      this.store.addLog("INFO", `文件回传完成: ${session.filename}`);
      // 通知 UI 刷新预览
      global.dispatchEvent(new CustomEvent("dsh:preview", { detail: this.store.previews[endResult.file_id] }));
    }
  }

  global.DSHTransfer = TransferClient;
})(window);
