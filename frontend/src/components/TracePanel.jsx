import { useState } from 'react'

function TraceStep({ step, index }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="step">
      <div className="stepHeader" onClick={() => setOpen(current => !current)}>
        <div className="stepTitle">
          {index + 1}. {step.step}
        </div>
        <div className="stepHeaderMeta">
          <div className="stepMeta">{step.tool || step.capability || ''}</div>
          <div className={`stepChevron ${open ? 'open' : ''}`}>v</div>
        </div>
      </div>
      {open && (
        <div className="stepBody">
          <pre>{JSON.stringify(step, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}

export default function TracePanel({ trace }) {
  if (!trace || trace.length === 0) {
    return (
      <section className="card">
        <h2>Agent Trace</h2>
        <p className="hint">Includes orchestration, MCP calls, and result previews. Click to expand.</p>
        <div className="trace muted">No trace yet.</div>
      </section>
    )
  }

  return (
    <section className="card">
      <h2>Agent Trace</h2>
      <p className="hint">Includes orchestration, MCP calls, and result previews. Click to expand.</p>
      <div className="trace">
        {trace.map((step, index) => (
          <TraceStep key={index} step={step} index={index} />
        ))}
      </div>
    </section>
  )
}
