import { useCallback, useEffect, useState } from 'react'
import { getMe, getStores, getToken, logout, setToken } from './api'
import AuthPage from './AuthPage'
import InventoryPage from './InventoryPage'
import RecommendationsPage from './RecommendationsPage'
import RulesPage from './RulesPage'
import ShopsPage from './ShopsPage'
import './App.css'

const TABS = [
  ['recs', 'Recommendations'],
  ['inventory', 'Inventory'],
  ['shops', 'My shops'],
  ['rules', 'Business rules'],
]

export default function App() {
  const [user, setUser] = useState(null)
  const [stores, setStores] = useState([])
  const [storesLoaded, setStoresLoaded] = useState(false)
  const [checking, setChecking] = useState(Boolean(getToken()))
  const [tab, setTab] = useState('recs')

  const refreshStores = useCallback(
    () =>
      getStores()
        .then(setStores)
        .catch(() => setStores([]))
        .finally(() => setStoresLoaded(true)),
    []
  )

  // restore the session on page load, and react to being signed out by the server
  useEffect(() => {
    if (!getToken()) return
    getMe()
      .then((me) => setUser(me.user))
      .catch(() => setToken(null))
      .finally(() => setChecking(false))
  }, [])
  useEffect(() => {
    const out = () => setUser(null)
    window.addEventListener('zwg-signed-out', out)
    return () => window.removeEventListener('zwg-signed-out', out)
  }, [])
  useEffect(() => {
    if (user) refreshStores()
    else {
      setStores([])
      setStoresLoaded(false)
    }
  }, [user, refreshStores])
  // someone with no shops yet is taken straight to the page where they can add one
  useEffect(() => {
    if (user && storesLoaded && stores.length === 0) setTab('shops')
  }, [user, storesLoaded, stores.length])

  async function signOut() {
    try {
      await logout()
    } catch {
      // the token is dropped locally either way
    }
    setToken(null)
    setUser(null)
    setTab('recs')
  }

  if (checking) return <div className="page"><p className="muted">Loading…</p></div>
  if (!user) return <AuthPage onSignedIn={setUser} />

  return (
    <div className="page wide">
      <header className="topbar">
        <div>
          <h1>Zero-Waste Grocery</h1>
          <nav className="tabs">
            {TABS.map(([key, label]) => (
              <button key={key} className={tab === key ? 'tab active' : 'tab'} onClick={() => setTab(key)}>
                {label}
              </button>
            ))}
          </nav>
        </div>
        <div className="account">
          <strong>{user.displayName}</strong>
          <span className="muted">
            {stores.length} shop{stores.length === 1 ? '' : 's'}
          </span>
          <button className="link" onClick={signOut}>Sign out</button>
        </div>
      </header>
      {tab === 'recs' && <RecommendationsPage planner={user.displayName} />}
      {tab === 'inventory' && <InventoryPage />}
      {tab === 'shops' && <ShopsPage stores={stores} onChanged={refreshStores} />}
      {tab === 'rules' && <RulesPage />}
    </div>
  )
}
