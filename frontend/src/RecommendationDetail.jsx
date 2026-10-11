import { useMemo, useState } from 'react'
import { sendDecision } from './api'
import { describeAction, inr } from './format'

export default function RecommendationDetail({ detail, planner, onChanged, onClose }) {
  const r = detail.recommendation
  const [mode, setMode] = useState(null) // null | modify | reject | feedback
  const [value, setValue] = useState('')
  const [comment, setComment] = useState('')
  const [rating, setRating] = useState('')
  const [waste, setWaste] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const evidence = useMemo(() => {
    try {
      return JSON.parse(detail.evidence)
    } catch {
      return null
    }
  }, [detail.evidence])

  async function run(action, body, message) {
    setBusy(true)
    setError('')
    try {
      const result = await sendDecision(r.recId, action, body)
      setMode(null)
      setComment('')
      setValue('')
      onChanged(typeof message === 'function' ? message(result) : message)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const by = { decidedBy: planner }
  const isMarkdown = r.actionType === 'MARKDOWN'
  const demand = evidence?.demand_agent
  const reasons = evidence?.reasons
  const batches = evidence?.freshness_agent?.batches ?? []

  return (
    <aside className="detail">
      <div className="detail-head">
        <div>
          <h2>
            {r.productName} · {r.storeName}
          </h2>
          <span className={`badge status-${r.status}`}>{r.status}</span>
        </div>
        <button className="link" onClick={onClose}>
          Close
        </button>
      </div>

      <p className="rationale">{r.rationale}</p>
      <dl className="facts">
        <dt>Action</dt>
        <dd>{describeAction(r)}</dd>
        <dt>When</dt>
        <dd>
          {r.actionDate} · {r.timingNote}
        </dd>
        <dt>Confidence</dt>
        <dd>{Math.round(r.confidence * 100)}%</dd>
        <dt>Expected effect</dt>
        <dd>{r.effectSummary}</dd>
      </dl>

      {reasons && (
        <section className="why">
          <h3>Why this is happening</h3>
          <p className="why-headline">{reasons.headline}</p>
          {reasons.drivers.length > 0 && (
            <ul className="drivers">
              {reasons.drivers.map((d) => (
                <li key={d.factor}>
                  <span className={`dir ${d.effect_pct == null ? 'flat' : d.effect_pct < 0 ? 'down' : 'up'}`}>
                    {d.effect_pct == null ? '•' : d.effect_pct < 0 ? '▼' : '▲'}
                  </span>
                  <span>{d.text}</span>
                </li>
              ))}
            </ul>
          )}
          {reasons.stock_facts.length > 0 && (
            <ul className="fact-list">
              {reasons.stock_facts.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          <p className="muted note">{reasons.note}</p>
        </section>
      )}

      {error && <div className="banner error">{error}</div>}

      {r.status === 'PROPOSED' && mode === null && (
        <div className="actions">
          <button className="btn primary" disabled={busy} onClick={() => run('approve', by, 'Approved')}>
            Approve
          </button>
          <button className="btn" onClick={() => setMode('modify')}>
            Modify
          </button>
          <button className="btn danger" onClick={() => setMode('reject')}>
            Reject
          </button>
        </div>
      )}
      {mode === 'modify' && (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault()
            const body = isMarkdown
              ? { ...by, comment, markdownPct: Number(value) }
              : { ...by, comment, quantity: Number(value) }
            run('modify', body, 'Modified')
          }}
        >
          <label>
            {isMarkdown ? 'New markdown (%)' : 'New quantity (units)'}
            <input type="number" min="1" step="any" required value={value} onChange={(e) => setValue(e.target.value)} />
          </label>
          <label>
            Comment (optional)
            <input value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div className="actions">
            <button className="btn primary" disabled={busy}>
              Save change
            </button>
            <button type="button" className="btn" onClick={() => setMode(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {mode === 'reject' && (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault()
            run('reject', { ...by, comment }, 'Rejected')
          }}
        >
          <label>
            Reason (required)
            <input required value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div className="actions">
            <button className="btn danger" disabled={busy}>
              Reject
            </button>
            <button type="button" className="btn" onClick={() => setMode(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {(r.status === 'APPROVED' || r.status === 'MODIFIED') && (
        <div className="actions">
          <button
            className="btn primary"
            disabled={busy}
            onClick={() =>
              run('execute', { executedBy: planner }, (res) =>
                res.accepted ? `Executed: ${res.system} ${res.reference}. ${res.message}` : `Rejected by ${res.system}: ${res.message}`
              )
            }
          >
            Execute in {isMarkdown ? 'POS' : r.actionType === 'TRANSFER' ? 'WMS' : 'ERP'}
          </button>
        </div>
      )}
      {r.status === 'EXECUTED' && mode === null && (
        <div className="actions">
          <button className="btn" onClick={() => setMode('feedback')}>
            Record outcome
          </button>
        </div>
      )}
      {mode === 'feedback' && (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault()
            run(
              'feedback',
              {
                comment,
                plannerRating: rating ? Number(rating) : null,
                actualWasteUnits: waste !== '' ? Number(waste) : null,
              },
              'Outcome recorded'
            )
          }}
        >
          <label>
            Rating (1-5)
            <input type="number" min="1" max="5" value={rating} onChange={(e) => setRating(e.target.value)} />
          </label>
          <label>
            Actual waste (units)
            <input type="number" min="0" step="any" value={waste} onChange={(e) => setWaste(e.target.value)} />
          </label>
          <label>
            Comment
            <input value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div className="actions">
            <button className="btn primary" disabled={busy}>
              Save outcome
            </button>
            <button type="button" className="btn" onClick={() => setMode(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      <h3>Options the agents compared</h3>
      <div className="table-wrap">
        <table className="small">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Option</th>
              <th className="num">Net benefit</th>
              <th className="num">Confidence</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {detail.options.map((o, i) => (
              <tr key={i} className={o.chosen ? 'row-chosen' : o.feasible ? '' : 'row-out'}>
                <td className="cap">{o.agent}</td>
                <td>
                  {o.actionType === 'MARKDOWN'
                    ? `${Number(o.markdownPct)}% off`
                    : `${o.quantity ?? '-'} units${o.counterpartStoreId ? ` → ${o.counterpartStoreId}` : ''}`}
                </td>
                <td className="num">{inr(o.expectedNetBenefit)}</td>
                <td className="num">{Math.round(o.confidence * 100)}%</td>
                <td>{o.chosen ? 'Chosen' : o.feasible ? 'Not best' : o.ruleNotes || 'Ruled out'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {demand && (
        <>
          <h3>Demand forecast (next 7 days)</h3>
          <div className="table-wrap">
            <table className="small">
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num">Expected</th>
                  <th className="num">Low (P10)</th>
                  <th className="num">High (P90)</th>
                </tr>
              </thead>
              <tbody>
                {demand.dates.map((d, i) => (
                  <tr key={d}>
                    <td>{d}</td>
                    <td className="num">{demand.mean[i]}</td>
                    <td className="num">{demand.p10[i]}</td>
                    <td className="num">{demand.p90[i]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {batches.length > 0 && (
        <>
          <h3>Batches on the shelf</h3>
          <div className="table-wrap">
            <table className="small">
              <thead>
                <tr>
                  <th>Batch</th>
                  <th className="num">Units</th>
                  <th className="num">Days left</th>
                  <th className="num">Expected unsold</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.batch_id}>
                    <td>{b.batch_id}</td>
                    <td className="num">{b.qty}</td>
                    <td className="num">{b.days_to_expiry}</td>
                    <td className="num">
                      {b.expected_unsold.toFixed(1)} ({b.unsold_pct.toFixed(0)}%)
                    </td>
                    <td>{b.risk_level}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3>Decision history</h3>
      {detail.decisions.length === 0 ? (
        <p className="muted">No decisions yet.</p>
      ) : (
        <ul className="history">
          {detail.decisions.map((d) => (
            <li key={d.logId}>
              <strong>{d.decision}</strong> by {d.decidedBy} · {d.decidedAt?.replace('T', ' ').slice(0, 16)}
              {d.comment && <span className="muted"> — {d.comment}</span>}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
