// Talks to the Spring Boot backend. Change VITE_API_URL in a .env file to point elsewhere.
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8080'

async function request(method, path, { params = {}, body } = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v != null)
  ).toString()
  const res = await fetch(`${BASE}${path}${query ? `?${query}` : ''}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).message ?? ''
    } catch {
      // response had no JSON body
    }
    throw new Error(`${detail || 'Request failed'} (${res.status})`)
  }
  return res.json()
}

// inventory
export const getStores = () => request('GET', '/api/stores')
export const getMeta = () => request('GET', '/api/meta')
export const getInventorySummary = (storeId, category) =>
  request('GET', '/api/inventory/summary', { params: { storeId, category } })

// recommendations and the planner workflow
export const getRecommendations = (params) => request('GET', '/api/recommendations', { params })
export const getRecommendationSummary = () => request('GET', '/api/recommendations/summary')
export const getRecommendation = (id) => request('GET', `/api/recommendations/${id}`)
// action: approve | reject | modify | execute | feedback
export const sendDecision = (id, action, body) =>
  request('POST', `/api/recommendations/${id}/${action}`, { body })

// business rules
export const getRules = () => request('GET', '/api/rules')
export const updateRule = (key, value) => request('PUT', `/api/rules/${key}`, { body: { value } })
