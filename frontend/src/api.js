// Talks to the Spring Boot backend. Change VITE_API_URL in a .env file to point elsewhere.
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8080'

async function get(path, params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v != null)
  ).toString()
  const res = await fetch(`${BASE}${path}${query ? `?${query}` : ''}`)
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).message ?? ''
    } catch {
      // response had no JSON body
    }
    throw new Error(`Request failed (${res.status}) ${detail}`.trim())
  }
  return res.json()
}

export const getStores = () => get('/api/stores')
export const getMeta = () => get('/api/meta')
export const getInventorySummary = (storeId, category) =>
  get('/api/inventory/summary', { storeId, category })
