import { useState } from 'react'
import InventoryPage from './InventoryPage'
import RecommendationsPage from './RecommendationsPage'
import RulesPage from './RulesPage'
import './App.css'

const TABS = [
  ['recs', 'Recommendations'],
  ['inventory', 'Inventory'],
  ['rules', 'Business rules'],
]

export default function App() {
  const [tab, setTab] = useState('recs')
  const [planner, setPlanner] = useState('planner1')

  return (
    <div className="page wide">
      <header className="topbar">
        <div>
          <h1>Zero-Waste Grocery · Planner</h1>
          <nav className="tabs">
            {TABS.map(([key, label]) => (
              <button key={key} className={tab === key ? 'tab active' : 'tab'} onClick={() => setTab(key)}>
                {label}
              </button>
            ))}
          </nav>
        </div>
        <label className="planner">
          Signed in as
          <input value={planner} onChange={(e) => setPlanner(e.target.value)} />
        </label>
      </header>
      {tab === 'recs' && <RecommendationsPage planner={planner || 'planner'} />}
      {tab === 'inventory' && <InventoryPage />}
      {tab === 'rules' && <RulesPage />}
    </div>
  )
}
