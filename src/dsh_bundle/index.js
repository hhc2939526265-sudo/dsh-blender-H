/**
 * dsh-blender-bridge · Host 插件
 *
 * 给模型三个工具，把 Blender 端插件（DSH Blender Bridge 1.1.9）的本地 WebSocket
 * 协议接到对话里：
 *   blender_status    读桥接状态（在线连接数 / 已注册命令数 / 插件版本）
 *   blender_commands  列出全部指令名（可按关键词过滤）
 *   blender_exec      执行一条指令（建模 / 动画 / 材质 / 特效 / 渲染 / 导出）
 *
 * 协议与端口默认 ws://127.0.0.1:8765，可在 bundle 配置里用 url 覆盖；
 * 若 Blender 面板设了连接口令，bundle 配置里用 token 填同一个值。
 */

import { defineTool } from '@deepseek-ai/dsh-tools'
import { BlenderBridgeClient } from './lib/bridge-client.js'

export const name = 'dsh-blender-bridge'
// cordis 依赖注入：不声明就 ctx.tools 拿不到（报 cannot get property "tools" without inject）
export const inject = ['tools']

const PROMPT_SECTION = 'Blender 桥接:本机 Blender 装了 DSH Blender Bridge 插件(本地端口 8765)。' +
  '涉及 3D 建模/动画/材质/特效/渲染/导出时:先 blender_status 确认在线,' +
  '用 blender_commands 查准命令名,再用 blender_exec 执行(command 为命令名,payload 为 JSON 字符串,字段随命令而定)。' +
  '命令返回 FAILED 就如实告诉用户原因,不要假装已经做完。'

function text(value, limit = 6000) {
  let body
  try {
    body = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  } catch {
    body = String(value)
  }
  if (body && body.length > limit) body = body.slice(0, limit) + '\n…(已截断)'
  return [{ type: 'text', text: body }]
}

function parsePayload(raw) {
  if (raw === undefined || raw === null || raw === '') return {}
  if (typeof raw === 'object') return raw
  const source = String(raw).trim()
  if (!source) return {}
  let parsed
  try {
    parsed = JSON.parse(source)
  } catch (error) {
    throw new Error('payload 不是合法 JSON：' + (error && error.message) + '；原始内容：' + source.slice(0, 300))
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('payload 必须是 JSON 对象（如 {"type":"cube"}）')
  }
  return parsed
}

export function apply(ctx, config) {
  const url = (config && typeof config.url === 'string' && config.url.trim()) || 'ws://127.0.0.1:8765'
  const token = (config && typeof config.token === 'string' && config.token.trim()) || ''
  const client = new BlenderBridgeClient({ url, token })

  ctx.tools.register(defineTool({
    name: 'blender_status',
    description: '查看 Blender 桥接状态：是否在线、连接数、已注册命令数、插件版本。' +
      '要用 Blender 做任何事之前先调用它确认端口 8765 上的插件在线。',
    output: { schema: { type: 'json' }, render: (_args, value) => text(value) },
    parameters: {},
    async execute() {
      try {
        const status = await client.status()
        return {
          ok: true,
          url,
          running: status.running,
          server: status.server,
          addon_version: status.version,
          connections: status.connections,
          command_count: Array.isArray(status.commands) ? status.commands.length : 0,
        }
      } catch (error) {
        return { ok: false, url, message: String((error && error.message) || error) }
      }
    },
  }))

  ctx.tools.register(defineTool({
    name: 'blender_commands',
    description: '列出 Blender 桥接插件注册的全部指令名，可按关键词过滤（如 mesh、anim、material、render）。' +
      '在 blender_exec 之前用它确认命令名，避免拼错。',
    parameters: {
      keyword: { type: 'string', description: '可选，按子串过滤命令名，如 "mesh" 或 "anim.keyframe"' },
    },
    output: { schema: { type: 'json' }, render: (_args, value) => text(value) },
    async execute(args) {
      try {
        const status = await client.status()
        const all = Array.isArray(status.commands) ? status.commands : []
        const keyword = String(args?.keyword || '').trim().toLowerCase()
        const matched = keyword ? all.filter((name) => String(name).toLowerCase().includes(keyword)) : all
        return {
          ok: true,
          total: all.length,
          matched: matched.length,
          commands: matched,
          groups: Array.from(new Set(matched.map((name) => String(name).split('.')[0]))),
        }
      } catch (error) {
        return { ok: false, url, message: String((error && error.message) || error) }
      }
    },
  }))

  ctx.tools.register(defineTool({
    name: 'blender_exec',
    description: '在 Blender 里执行一条桥接指令，例如 mesh.add_primitive（建模）、material.pbr_generate（材质）、' +
      'anim.keyframe（关键帧）、effect.*（特效）、render.execute（渲染）、export.scene（导出）。' +
      'command 用 blender_commands 查到的命令名；payload 是 JSON 字符串，字段随命令而定，例如 {"type":"cube","name":"Box"}。',
    parameters: {
      command: { type: 'string', description: '命令名，如 mesh.add_primitive' },
      payload: { type: 'string', description: '可选，JSON 字符串形式的参数对象，如 {"type":"cube"}' },
    },
    output: { schema: { type: 'json' }, render: (_args, value) => text(value) },
    async execute(args) {
      const command = String(args?.command || '').trim()
      if (!command) return { ok: false, message: 'command 不能为空' }
      let payload
      try {
        payload = parsePayload(args?.payload)
      } catch (error) {
        return { ok: false, message: String((error && error.message) || error) }
      }
      try {
        const response = await client.request(command, payload)
        const ok = response.status === 'SUCCESS'
        return {
          ok,
          command,
          status: response.status,
          result: response.result,
          error: response.error || null,
        }
      } catch (error) {
        return { ok: false, command, message: String((error && error.message) || error) }
      }
    },
  }))

  // 让模型知道桥接存在，不必等用户先提 Blender。
  try {
    ctx.on('system-prompt/assemble', async (assembly, _context, next) => {
      const assembled = await next()
      try {
        assembled.sections.push({ name: 'dsh-blender-bridge:hint', text: PROMPT_SECTION })
      } catch {
        /* 装配结构变化时静默跳过 */
      }
      return assembled
    })
  } catch {
    /* 宿主没有该事件时不影响工具使用 */
  }

  try {
    ctx.on('dispose', () => client.close())
  } catch {
    /* ignore */
  }
}
