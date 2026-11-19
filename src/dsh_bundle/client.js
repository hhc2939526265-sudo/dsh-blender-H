/**
 * dsh-blender-bridge · Client 插件（输入框左侧状态胶囊）
 *
 * 直接连 ws://127.0.0.1:8765（浏览器 WebSocket 允许跨端口，页面本身在 127.0.0.1），
 * 用 system.status 指令拿在线状态，每 5s 重连一次。点击胶囊可立即重试。
 * 注册 id 必须与 loader entry 名一致（dsh-blender-bridge）。
 */
window.__ModuleLoader__.load({
  id: 'dsh-blender-bridge',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })

    const React = require('react')

    const BRIDGE_URL = 'ws://127.0.0.1:8765'
    const POLL_MS = 5000

    const chipStyle = {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      height: '28px',
      padding: '0 10px',
      borderRadius: '14px',
      border: '1px solid var(--dsw-alias-border-l1)',
      background: 'transparent',
      color: 'var(--dsw-alias-label-secondary)',
      fontSize: '12px',
      lineHeight: '1',
      cursor: 'pointer',
      whiteSpace: 'nowrap',
    }

    const dotStyle = (phase) => ({
      width: '8px',
      height: '8px',
      borderRadius: '4px',
      flex: 'none',
      background: phase === 'online' ? '#22c55e' : phase === 'connecting' ? '#f59e0b' : '#9ca3af',
    })

    function StatusChip() {
      const [state, setState] = React.useState({ phase: 'connecting', info: null })
      const [nonce, setNonce] = React.useState(0)

      React.useEffect(() => {
        let ws = null
        let timer = null
        let alive = true

        const schedule = () => {
          if (!alive) return
          clearTimeout(timer)
          timer = setTimeout(open, POLL_MS)
        }

        function open() {
          if (!alive) return
          setState((prev) => (prev.phase === 'online' ? prev : { phase: 'connecting', info: null }))
          try {
            ws = new WebSocket(BRIDGE_URL)
          } catch {
            setState({ phase: 'offline', info: null })
            schedule()
            return
          }
          ws.onopen = () => {
            try {
              // system.status 只由服务端主动推送，这里是握手指令，回帧带指令清单
              ws.send(JSON.stringify({
                cmd_id: 'ui-' + Date.now(),
                cmd_type: 'system.handshake',
                payload: {},
                status: 'PENDING',
                result: null,
                error: null,
              }))
            } catch {
              /* ignore */
            }
          }
          ws.onmessage = (event) => {
            try {
              const msg = JSON.parse(event.data)
              if (!msg) return
              if (msg.cmd_type === 'system.handshake' && msg.result) {
                setState({
                  phase: 'online',
                  info: {
                    commands: Array.isArray(msg.result.commands) ? msg.result.commands : [],
                    version: msg.result.version,
                  },
                })
              } else if (msg.cmd_type === 'system.status' && msg.result) {
                setState((prev) => prev.phase === 'online'
                  ? prev
                  : { phase: 'online', info: { commands: [], version: '' } })
              }
            } catch {
              /* ignore */
            }
          }
          ws.onerror = () => {
            if (!alive) return
            setState((prev) => (prev.phase === 'online' ? prev : { phase: 'offline', info: null }))
          }
          ws.onclose = () => {
            if (!alive) return
            setState({ phase: 'offline', info: null })
            schedule()
          }
        }

        open()
        return () => {
          alive = false
          clearTimeout(timer)
          try { if (ws) ws.close() } catch { /* ignore */ }
        }
      }, [nonce])

      const phase = state.phase
      const count = state.info && Array.isArray(state.info.commands) ? state.info.commands.length : 0
      const label = phase === 'online'
        ? 'Blender · ' + count + ' 命令'
        : phase === 'connecting' ? 'Blender 连接中' : 'Blender 未连接'
      const version = state.info && state.info.version ? String(state.info.version) : ''
      const title = phase === 'online'
        ? '已连接 ' + BRIDGE_URL + '（插件 v' + (version || '?') + '）；点击重连'
        : '未连接 ' + BRIDGE_URL + '。在 Blender 的 3D 视图按 N 打开侧栏 → DSH Bridge → 点「启动服务」；点击这里重试'

      return React.createElement(
        'button',
        {
          type: 'button',
          style: chipStyle,
          title,
          onClick: () => setNonce((n) => n + 1),
        },
        React.createElement('span', { style: dotStyle(phase) }),
        React.createElement('span', null, label),
      )
    }

    const inject = ['slots', 'workspaces']

    function apply(ctx) {
      const slots = ctx.get('slots')
      if (slots === undefined) return
      slots.inject('conversation.input.left', () => slots.register(
        { name: 'conversation.input.left', id: 'blender-bridge', order: 6, label: 'Blender 桥接' },
        () => React.createElement(StatusChip),
      ))
    }

    exports.apply = apply
    exports.inject = inject
    return module.exports
  },
})
