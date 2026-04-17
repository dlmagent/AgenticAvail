import { useEffect, useState } from 'react'
import { apiUrl } from './api'
import ChatPanel from './components/ChatPanel'
import Toolbar from './components/Toolbar'
import TracePanel from './components/TracePanel'

export default function App() {
  const [theme, setTheme] = useState('dark')
  const [trace, setTrace] = useState([])
  const [health, setHealth] = useState({ ok: false, model: null })
  const [sessionId, setSessionId] = useState('demo-1')
  const [hasMessages, setHasMessages] = useState(false)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    async function ping() {
      try {
        const response = await fetch(apiUrl('/health'))
        const payload = await response.json()
        setHealth({ ok: response.ok, model: payload.model || null })
      } catch {
        setHealth({ ok: false, model: null })
      }
    }

    ping()
    const intervalId = setInterval(ping, 4000)
    return () => clearInterval(intervalId)
  }, [])

  return (
    <>
      <Toolbar
        theme={theme}
        onToggle={() => setTheme(current => (current === 'dark' ? 'light' : 'dark'))}
        sessionId={sessionId}
        onSessionChange={setSessionId}
      />

      <div className={`app ${hasMessages ? 'app--active' : 'app--empty'}`}>
        {hasMessages && (
          <header className="header">
            <div>
              <h2>Agentic Hotel Search</h2>
              <p className="sub">React frontend talking to one unified backend that hosts orchestration, MCP, and domain agents.</p>
            </div>
            <div className="status">
              <span className="dot" style={{ background: health.ok ? '#2ecc71' : '#e74c3c' }} />
              <span>{health.ok ? `Online${health.model ? ` | ${health.model}` : ''}` : 'Checking...'}</span>
            </div>
          </header>
        )}

        {!hasMessages && (
          <div className="empty-state">
            <h1>Agentic Hotel Search</h1>
            <p className="sub">Ask for a hotel in Atlanta for June 2026</p>
            <div className="status" style={{ justifyContent: 'center', marginTop: 8 }}>
              <span className="dot" style={{ background: health.ok ? '#2ecc71' : '#e74c3c' }} />
              <span>{health.ok ? `Online${health.model ? ` | ${health.model}` : ''}` : 'Checking...'}</span>
            </div>
          </div>
        )}

        <main className={hasMessages ? 'grid' : 'grid-empty'}>
          <ChatPanel sessionId={sessionId} onTrace={setTrace} onHasMessages={setHasMessages} />
          {hasMessages && <TracePanel trace={trace} />}
        </main>

        {hasMessages && (
          <footer className="footer">
            <div className="hint">
              Try: <code>must have pool</code> | <code>prefer spa</code> | <code>cheapest total</code> | <code>best rated</code>
            </div>
          </footer>
        )}
      </div>
    </>
  )
}
