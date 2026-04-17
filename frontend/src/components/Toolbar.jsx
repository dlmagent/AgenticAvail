export default function Toolbar({ theme, onToggle, sessionId, onSessionChange }) {
  const isLight = theme === 'light'

  return (
    <div className="toolbar">
      <label className="theme-switch" title="Toggle light and dark mode">
        <span className={`theme-track ${isLight ? 'checked' : ''}`} onClick={onToggle}>
          <span className="theme-thumb" />
        </span>
        <span className="theme-icon">{isLight ? 'Sun' : 'Moon'}</span>
      </label>
      <div className="toolbar-session">
        <span className="toolbar-session-label">Session</span>
        <input
          className="toolbar-input"
          value={sessionId}
          onChange={event => onSessionChange(event.target.value)}
          spellCheck={false}
        />
      </div>
    </div>
  )
}
