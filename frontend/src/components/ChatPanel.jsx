import { useEffect, useRef, useState } from 'react'
import { apiUrl } from '../api'

const PLACEHOLDER =
  'Find me a hotel in Atlanta June 10-13 2026 for 2 rooms and 4 guests. Must have a swimming pool. Prefer spa. Cheapest total.'

export default function ChatPanel({ sessionId, onTrace, onHasMessages }) {
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [micState, setMicState] = useState('idle')
  const [micStatus, setMicStatus] = useState('')
  const chatRef = useRef(null)
  const recognitionRef = useRef(null)
  const textareaRef = useRef(null)

  const hasMessages = messages.length > 0

  useEffect(() => {
    document.body.classList.toggle('waiting', loading)
  }, [loading])

  useEffect(() => {
    onHasMessages(hasMessages)
  }, [hasMessages, onHasMessages])

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight
    }
  }, [messages])

  function addMessage(who, text) {
    setMessages(previous => [...previous, { who, text }])
  }

  async function send() {
    const text = message.trim()
    if (!text || loading) return

    setLoading(true)
    addMessage('You', text)
    setMessage('')

    try {
      const response = await fetch(apiUrl('/chat/react'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId || 'demo-1', message: text }),
      })
      const raw = await response.text()
      if (!response.ok) {
        addMessage('Assistant', `Backend error (${response.status}):\n${raw}`)
        onTrace([])
        return
      }

      const payload = JSON.parse(raw)
      addMessage('Assistant', payload.assistant_message || '(no response)')
      onTrace(payload.trace || [])
    } catch {
      addMessage('Assistant', 'Error calling /chat. Is the unified backend running?')
      onTrace([])
    } finally {
      setLoading(false)
      textareaRef.current?.focus()
    }
  }

  function handleKeyDown(event) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault()
      send()
      return
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      send()
    }
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition

  function initRecognition() {
    if (!SpeechRecognition) return null

    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    let lastInterim = ''

    recognition.onstart = () => {
      lastInterim = ''
      setMicState('listening')
      setMicStatus('Listening...')
    }
    recognition.onend = () => {
      setMicState('idle')
      setMicStatus('')
    }
    recognition.onerror = event => {
      setMicState('idle')
      setMicStatus(`Mic error: ${event.error || 'unknown'}`)
    }
    recognition.onresult = event => {
      let interim = ''
      let finalText = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        const transcript = result[0]?.transcript || ''
        if (result.isFinal) finalText += transcript
        else interim += transcript
      }
      if (finalText.trim()) {
        setMessage(current => {
          const separator = current.trim().length === 0 ? '' : current.endsWith(' ') ? '' : ' '
          return current + separator + finalText.trim()
        })
      }
      const cleanInterim = interim.trim()
      if (cleanInterim && cleanInterim !== lastInterim) {
        setMicStatus(`Listening... (${cleanInterim})`)
        lastInterim = cleanInterim
      } else if (!cleanInterim) {
        setMicStatus('Listening...')
      }
    }

    return recognition
  }

  function toggleMic() {
    if (!SpeechRecognition) return
    if (micState === 'listening') {
      recognitionRef.current?.stop()
      return
    }
    if (!recognitionRef.current) recognitionRef.current = initRecognition()
    try {
      recognitionRef.current.start()
    } catch {
      setMicStatus('Mic busy, try again.')
    }
  }

  function clearChat() {
    setMessages([])
    onTrace([])
    textareaRef.current?.focus()
  }

  return (
    <div className={`chat-panel ${hasMessages ? 'has-messages' : 'empty'}`}>
      {hasMessages && (
        <div className="chat-history card" ref={chatRef}>
          {messages.map((entry, index) => (
            <div key={index} className={`bubble ${entry.who === 'You' ? 'user' : 'assistant'}`}>
              <div className="who">{entry.who}</div>
              <div className="text">{entry.text}</div>
            </div>
          ))}
        </div>
      )}

      <div className={`input-bar${loading ? ' loading' : ''}`}>
        <div className="textarea-wrap">
          <textarea
            ref={textareaRef}
            rows={3}
            autoFocus
            placeholder={PLACEHOLDER}
            value={message}
            onChange={event => setMessage(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
        </div>
        <div className="actions">
          <button onClick={send} disabled={loading}>
            Send
          </button>
          <button
            className={`secondary${micState === 'listening' ? ' mic-active' : ''}`}
            onClick={toggleMic}
            disabled={!SpeechRecognition}
            title="Dictate message using your microphone"
          >
            {micState === 'listening' ? 'Stop' : 'Dictate'}
          </button>
          {hasMessages && (
            <button className="secondary" onClick={clearChat}>
              Clear
            </button>
          )}
          <span className="muted status-inline">{micStatus}</span>
          {loading && (
            <div className="thinking">
              <span className="spinner" />
              <span className="thinking-text">Thinking...</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
