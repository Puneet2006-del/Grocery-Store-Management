import { useEffect, useMemo, useState } from 'react'
import { getInventorySummary, getMeta, getStores } from './api'

const CATEGORIES = ['produce', 'dairy', 'bakery', 'meat']

// Most urgent first: expired, critical, out of stock, warning, ok
const URGENCY = { EXPIRED: 0, CRITICAL: 1, OUT_OF_STOCK: 2, WARNING: 3, OK: 4 }

const STATUS_LABEL = {
  EXPIRED: 'Expired',
  CRITICAL: 'Expires ≤ 1 day',
  WARNING: 'Expires ≤ 3 days',
  OK: 'Fresh',
  OUT_OF_STOCK: 'Out of stock',
}

export default function InventoryPage() {
  const [stores, setStores] = useState([])
  const [asOf, setAsOf] = useState('')
  const [rows, setRows] = useState([])
  const [storeId, setStoreId] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // stores and the "as of" date load once
  useEffect(() => {
    Promise.all([getStores(), getMeta()])
      .then(([s, m]) => {
        setStores(s)
        setAsOf(m.asOfDate)
      })
      .catch((e) => setError(e.message))
  }, [])

  // inventory reloads whenever the store or category filter changes
  useEffect(() => {
    let cancelled = false
    getInventorySummary(storeId, category)
      .then((data) => {
        if (!cancelled) {
          setRows(data)
          setError('')
          setLoading(false)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [storeId, category])

  const counts = useMemo(() => {
    const c = { EXPIRED: 0, CRITICAL: 0, OUT_OF_STOCK: 0, WARNING: 0, OK: 0 }
    rows.forEach((r) => {
      c[r.status] = (c[r.status] ?? 0) + 1
    })
    return c
  }, [rows])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows
      .filter((r) => !status || r.status === status)
      .filter((r) => !q || r.productName.toLowerCase().includes(q) || r.skuId.toLowerCase().includes(q))
      .sort(
        (a, b) =>
          URGENCY[a.status] - URGENCY[b.status] ||
          (a.daysToExpiry ?? 0) - (b.daysToExpiry ?? 0) ||
          a.storeId.localeCompare(b.storeId)
      )
  }, [rows, status, search])

  const changeStore = (v) => {
    setLoading(true)
    setStoreId(v)
  }
  const changeCategory = (v) => {
    setLoading(true)
    setCategory(v)
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Perishable Inventory</h1>
          <p className="muted">Zero-Waste Grocery{asOf && ` · data as of ${asOf}`}</p>
        </div>
      </header>

      <section className="filters">
        <label>
          Store
          <select value={storeId} onChange={(e) => changeStore(e.target.value)}>
            <option value="">All stores</option>
            {stores.map((s) => (
              <option key={s.storeId} value={s.storeId}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Category
          <select value={category} onChange={(e) => changeCategory(e.target.value)}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c[0].toUpperCase() + c.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          Search
          <input
            type="search"
            placeholder="Product name or SKU"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </section>

      <section className="chips">
        <button className={`chip ${status === '' ? 'active' : ''}`} onClick={() => setStatus('')}>
          All ({rows.length})
        </button>
        {Object.keys(URGENCY).map((s) => (
          <button
            key={s}
            className={`chip chip-${s} ${status === s ? 'active' : ''}`}
            onClick={() => setStatus(status === s ? '' : s)}
          >
            {STATUS_LABEL[s]} ({counts[s] ?? 0})
          </button>
        ))}
      </section>

      {error && <div className="banner error">Could not load data: {error}</div>}
      {loading && <div className="banner">Loading inventory…</div>}

      {!loading && !error && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Store</th>
                <th>SKU</th>
                <th>Product</th>
                <th>Category</th>
                <th className="num">On hand</th>
                <th className="num">Batches</th>
                <th>Nearest expiry</th>
                <th className="num">Days left</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={`${r.storeId}-${r.skuId}`} className={`row-${r.status}`}>
                  <td>{r.storeName}</td>
                  <td>{r.skuId}</td>
                  <td>{r.productName}</td>
                  <td className="cap">{r.category}</td>
                  <td className="num">
                    {r.onHandQty} {r.unit}
                  </td>
                  <td className="num">{r.batchCount}</td>
                  <td>{r.nearestExpiry ?? '—'}</td>
                  <td className="num">{r.daysToExpiry ?? '—'}</td>
                  <td>
                    <span className={`badge badge-${r.status}`}>{STATUS_LABEL[r.status]}</span>
                  </td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={9} className="empty">
                    No items match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
