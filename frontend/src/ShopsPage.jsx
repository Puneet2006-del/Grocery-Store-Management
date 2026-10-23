import { useEffect, useState } from 'react'
import { createShop, retryShop } from './api'

const sizeLabel = (f) => (Number(f) < 0.85 ? 'Small' : Number(f) <= 1.15 ? 'Medium' : 'Large')

export default function ShopsPage({ stores, onChanged }) {
  const [form, setForm] = useState({ name: '', city: '', type: 'urban', size: 'medium', latitude: '', longitude: '' })
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = stores.some((s) => s.status === 'PENDING')

  // while a new shop is being set up, check on it every few seconds
  useEffect(() => {
    if (!pending) return undefined
    const timer = setInterval(onChanged, 4000)
    return () => clearInterval(timer)
  }, [pending, onChanged])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError('Your browser cannot share its location. Enter the latitude and longitude by hand.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        setForm((f) => ({ ...f, latitude: pos.coords.latitude.toFixed(5), longitude: pos.coords.longitude.toFixed(5) })),
      () => setError('Could not get your location. Enter the latitude and longitude by hand.')
    )
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const shop = await createShop({ ...form, latitude: Number(form.latitude), longitude: Number(form.longitude) })
      setInfo(`${shop.name} was added. Its history and forecasts are being created; this takes a few minutes.`)
      setForm({ name: '', city: '', type: 'urban', size: 'medium', latitude: '', longitude: '' })
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function retry(id) {
    try {
      await retryShop(id)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2 className="section-title">Your shops</h2>
      {stores.length === 0 && <p className="muted">You have not added a shop yet. Add your first one below.</p>}
      <div className="shops">
        {stores.map((s) => (
          <div className="shop-card" key={s.storeId}>
            <div className="shop-head">
              <strong>{s.name}</strong>
              <span className={`badge shop-${s.status}`}>{s.status === 'READY' ? 'Ready' : s.status === 'PENDING' ? 'Setting up' : 'Failed'}</span>
            </div>
            <div className="muted">{s.city} · {s.type} · {sizeLabel(s.sizeFactor)}</div>
            {s.status === 'PENDING' && <div className="progress"><span className="spinner" /> {s.statusMessage}</div>}
            {s.status === 'FAILED' && (
              <div>
                <div className="banner error">{s.statusMessage}</div>
                <button className="btn" onClick={() => retry(s.storeId)}>Try again</button>
              </div>
            )}
          </div>
        ))}
      </div>

      <h2 className="section-title">Add a shop</h2>
      <form className="form shop-form" onSubmit={submit}>
        <label>
          Shop name
          <input required value={form.name} onChange={set('name')} placeholder="For example: Green Mart, Sector 14" />
        </label>
        <label>
          City
          <input required value={form.city} onChange={set('city')} placeholder="For example: Faridabad" />
        </label>
        <div className="row">
          <label>
            Type
            <select value={form.type} onChange={set('type')}>
              <option value="urban">Urban</option>
              <option value="suburban">Suburban</option>
            </select>
          </label>
          <label>
            Size
            <select value={form.size} onChange={set('size')}>
              <option value="small">Small</option>
              <option value="medium">Medium</option>
              <option value="large">Large</option>
            </select>
          </label>
        </div>
        <div className="row">
          <label>
            Latitude
            <input required type="number" step="any" value={form.latitude} onChange={set('latitude')} />
          </label>
          <label>
            Longitude
            <input required type="number" step="any" value={form.longitude} onChange={set('longitude')} />
          </label>
        </div>
        <button type="button" className="link" onClick={useMyLocation}>Use my current location</button>
        <p className="muted note">
          The location is used for weather and to work out distances for moving stock between your shops. A new shop starts
          with 12 weeks of simulated history; in a real deployment you would import the shop's own sales instead.
        </p>
        {error && <div className="banner error">{error}</div>}
        {info && <div className="banner ok">{info}</div>}
        <button className="btn primary" disabled={busy}>Add shop</button>
      </form>
    </div>
  )
}
