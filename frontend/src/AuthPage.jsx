import { useState } from 'react'
import { login, register, setToken } from './api'

export default function AuthPage({ onSignedIn }) {
  const [mode, setMode] = useState('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = mode === 'login' ? await login(email, password) : await register(email, password, name)
      setToken(res.token)
      onSignedIn(res.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <form className="auth-card" onSubmit={submit}>
        <h1>Zero-Waste Grocery</h1>
        <p className="muted">Keep fresh stock selling, not expiring.</p>
        <div className="tabs">
          <button type="button" className={mode === 'login' ? 'tab active' : 'tab'} onClick={() => setMode('login')}>
            Sign in
          </button>
          <button type="button" className={mode === 'register' ? 'tab active' : 'tab'} onClick={() => setMode('register')}>
            Create account
          </button>
        </div>
        {mode === 'register' && (
          <label>
            Your name or business name
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        <label>
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password {mode === 'register' && <span className="muted">(at least 8 characters)</span>}
          <input type="password" required minLength={mode === 'register' ? 8 : 1} value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="banner error">{error}</div>}
        <button className="btn primary wide" disabled={busy}>
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
        {mode === 'login' && <p className="muted hint">Demo accounts: delhi@demo.com or ncr@demo.com, password demo12345</p>}
      </form>
    </div>
  )
}
