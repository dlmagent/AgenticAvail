const apiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || ''

export function apiUrl(path) {
  if (!apiBase) return path
  return `${apiBase}${path.startsWith('/') ? path : `/${path}`}`
}
