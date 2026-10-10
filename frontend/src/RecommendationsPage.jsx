import { useCallback, useEffect, useState } from 'react'
import { getRecommendation, getRecommendations, getRecommendationSummary, getStores } from './api'
import RecommendationDetail from './RecommendationDetail'
import { describeAction, inr } from './format'

const STATUSES = ['PROPOSED', 'APPROVED', 'MODIFIED', 'REJECTED', 'EXECUTED']
const ACTIONS = ['MARKDOWN', 'TRANSFER', 'REPLENISH']

export default function RecommendationsPage({ planner }) {
  const [recs, setRecs] = useState([])
  const [summary, setSummary] = useState(null)
  const [stores, setStores] = useState([])
  const [filters, setFilters] = useState({ status: '', actionType: '', storeId: '' })
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  const load = useCallback(async () => {
    try {
      const [list, sum] = await Promise.all([getRecommendations(filters), getRecommendationSummary()])
      setRecs(list)
      setSummary(sum)
      setError('')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    getStores().then(setStores).catch(() => {})
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (selected == null) return
    getRecommendation(selected)
      .then(setDetail)
      .catch((e) => setError(e.message))
  }, [selected])

  function changed(message) {
    setToast(message)
    load()
    if (selected != null) getRecommendation(selected).then(setDetail)
  }

  const byStatus = summary?.byStatus ?? {}
  const totals = Object.values(summary?.byAction ?? {}).reduce(
    (t, a) => ({ benefit: t.benefit + Number(a.expectedNetBenefit), waste: t.waste + Number(a.expectedWasteAvoidedUnits) }),
    { benefit: 0, waste: 0 }
  )
  const setFilter = (k, v) => {
    setLoading(true)
    setFilters({ ...filters, [k]: v })
  }

  return (
    <div className={`split ${detail ? 'open' : ''}`}>
      <section>
        <div className="cards">
          <div className="card">
            <span>Awaiting review</span>
            <strong>{byStatus.PROPOSED ?? 0}</strong>
          </div>
          <div className="card">
            <span>Ready to execute</span>
            <strong>{(byStatus.APPROVED ?? 0) + (byStatus.MODIFIED ?? 0)}</strong>
          </div>
          <div className="card">
            <span>Executed</span>
            <strong>{byStatus.EXECUTED ?? 0}</strong>
          </div>
          <div className="card">
            <span>Expected net benefit</span>
            <strong>{inr(totals.benefit)}</strong>
          </div>
          <div className="card">
            <span>Waste avoided (units)</span>
            <strong>{totals.waste.toFixed(0)}</strong>
          </div>
        </div>

        <section className="filters">
          <label>
            Status
            <select value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            Action
            <select value={filters.actionType} onChange={(e) => setFilter('actionType', e.target.value)}>
              <option value="">All</option>
              {ACTIONS.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            Store
            <select value={filters.storeId} onChange={(e) => setFilter('storeId', e.target.value)}>
              <option value="">All stores</option>
              {stores.map((s) => (
                <option key={s.storeId} value={s.storeId}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </section>

        {toast && (
          <div className="banner ok" onClick={() => setToast('')}>
            {toast}
          </div>
        )}
        {error && <div className="banner error">Could not load data: {error}</div>}
        {loading && <div className="banner">Loading recommendations…</div>}

        {!loading && !error && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Store</th>
                  <th>Product</th>
                  <th>Recommended action</th>
                  <th className="num">Confidence</th>
                  <th className="num">Net benefit</th>
                  <th className="num">Waste avoided</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recs.map((r) => (
                  <tr
                    key={r.recId}
                    className={`clickable ${selected === r.recId ? 'row-selected' : ''}`}
                    onClick={() => setSelected(r.recId)}
                  >
                    <td>{r.storeName}</td>
                    <td>{r.productName}</td>
                    <td>
                      <span className={`badge action-${r.actionType}`}>{r.actionType}</span> {describeAction(r)}
                    </td>
                    <td className="num">{Math.round(r.confidence * 100)}%</td>
                    <td className="num">{inr(r.expectedNetBenefit)}</td>
                    <td className="num">{Number(r.expectedWasteAvoidedUnits).toFixed(0)}</td>
                    <td>
                      <span className={`badge status-${r.status}`}>{r.status}</span>
                    </td>
                  </tr>
                ))}
                {recs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty">
                      No recommendations match. To generate them, run: python agents\orchestrator.py
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {detail && (
        <RecommendationDetail
          key={detail.recommendation.recId + detail.recommendation.status}
          detail={detail}
          planner={planner}
          onChanged={changed}
          onClose={() => {
            setDetail(null)
            setSelected(null)
          }}
        />
      )}
    </div>
  )
}
