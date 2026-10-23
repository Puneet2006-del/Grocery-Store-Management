// Talks to the Spring Boot backend. Change VITE_API_URL in a .env file to point elsewhere.
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8080'

const TOKEN_KEY = 'zwg_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY))

async function request(method, path, { params = {}, body } = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v != null)
  ).toString()
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  if (getToken()) headers.Authorization = `Bearer ${getToken()}`
  const res = await fetch(`${BASE}${path}${query ? `?${query}` : ''}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    // the session ended or the token is no longer valid: go back to the sign-in screen
    setToken(null)
    window.dispatchEvent(new Event('zwg-signed-out'))
  }
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

// accounts
export const register = (email, password, displayName) =>
  request('POST', '/api/auth/register', { body: { email, password, displayName } })
export const login = (email, password) => request('POST', '/api/auth/login', { body: { email, password } })
export const logout = () => request('POST', '/api/auth/logout')
export const getMe = () => request('GET', '/api/auth/me')

// shops
export const createShop = (body) => request('POST', '/api/stores', { body })
export const retryShop = (id) => request('POST', `/api/stores/${id}/retry`)

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
export const resetRule = (key) => request('DELETE', `/api/rules/${key}`)
