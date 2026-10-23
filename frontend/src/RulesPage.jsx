import { useEffect, useState } from 'react'
import { getRules, resetRule, updateRule } from './api'

export default function RulesPage() {
  const [rules, setRules] = useState([])
  const [edits, setEdits] = useState({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  useEffect(() => {
    getRules()
      .then(setRules)
      .catch((e) => setError(e.message))
  }, [])

  async function save(rule) {
    try {
      const updated = await updateRule(rule.key, edits[rule.key])
      setRules(rules.map((r) => (r.key === updated.key ? updated : r)))
      setEdits({ ...edits, [rule.key]: undefined })
      setError('')
      setSaved(`${rule.key} updated. The agents use the new value the next time they run.`)
    } catch (e) {
      setError(e.message)
    }
  }

  async function reset(rule) {
    try {
      const updated = await resetRule(rule.key)
      setRules(rules.map((r) => (r.key === updated.key ? updated : r)))
      setEdits({ ...edits, [rule.key]: undefined })
      setError('')
      setSaved(`${rule.key} is back to the default.`)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div>
      <p className="muted">Your business rules. They apply only to your shops, and the agents use the new values the next time they run.</p>
      {saved && <div className="banner ok">{saved}</div>}
      {error && <div className="banner error">{error}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rule</th>
              <th>Value</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => {
              const edited = edits[r.key] !== undefined && edits[r.key] !== r.value
              return (
                <tr key={r.key}>
                  <td>{r.key}</td>
                  <td>
                    <input
                      className="rule-input"
                      value={edits[r.key] ?? r.value}
                      onChange={(e) => setEdits({ ...edits, [r.key]: e.target.value })}
                    />{' '}
                    {edited && (
                      <button className="btn primary" onClick={() => save(r)}>
                        Save
                      </button>
                    )}
                    {!edited && r.customised && (
                      <button className="link" onClick={() => reset(r)}>
                        Reset to default
                      </button>
                    )}
                  </td>
                  <td className="muted wrap">{r.description}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
