function escapeHtml(s: string) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const SENSITIVE_KEYS = new Set([
  'authorization', 'authorization_header', 'set-cookie', 'cookie', 'password', 'passwd', 'secret', 'token', 'access_token', 'refresh_token', 'client_secret', 'api_key', 'apikey', 'connection_string'
])

const JWT_RE = /eyJ[\w-\-_=]+?\.[\w-\-_=]+?\.[\w-\-_=]+?/i
const BEARER_RE = /bearer\s+[A-Za-z0-9\-_.\=\+/]+/i
const LONG_TOKEN_RE = /[A-Za-z0-9_\-]{20,}/g

function maskLongToken(t: string) {
  if (t.length <= 8) return '****'
  const head = t.slice(0, 6)
  const tail = t.slice(-4)
  return `${head}...${tail}`
}

function maskString(s: string) {
  if (!s) return s
  // mask JWT
  s = s.replace(JWT_RE, (m) => maskLongToken(m))
  // mask bearer
  s = s.replace(BEARER_RE, (m) => m.split(' ')[0] + ' ****')
  // mask other long tokens
  s = s.replace(LONG_TOKEN_RE, (m) => (m.length > 24 ? maskLongToken(m) : m))
  return s
}

function truncateLines(s: string, maxLines = 200, maxChars = 2000) {
  const lines = s.split(/\r?\n/)
  const taken = lines.slice(0, maxLines)
  let out = taken.join('\n')
  if (s.length > maxChars) out = out.slice(0, maxChars) + '\n... (truncated)'
  return out
}

function sanitizeObject(obj: any, depth = 0): any {
  if (depth > 6) return '...'
  if (obj === null || obj === undefined) return obj
  if (typeof obj === 'string') {
    const masked = maskString(obj)
    return truncateLines(masked, 200, 2000)
  }
  if (typeof obj === 'number' || typeof obj === 'boolean') return obj
  if (Array.isArray(obj)) return obj.map((v) => sanitizeObject(v, depth + 1))
  if (typeof obj === 'object') {
    const out: any = {}
    for (const k of Object.keys(obj)) {
      try {
        const lk = String(k).toLowerCase()
        if (SENSITIVE_KEYS.has(lk)) {
          out[k] = '***masked***'
        } else {
          out[k] = sanitizeObject(obj[k], depth + 1)
        }
      } catch (e) {
        out[k] = 'error'
      }
    }
    return out
  }
  return String(obj)
}

export default function sanitizeError(raw: any): string {
  try {
    if (raw === undefined || raw === null) return ''
    // If it's already an object, sanitize recursively
    if (typeof raw === 'object') {
      const sanitized = sanitizeObject(raw)
      const json = JSON.stringify(sanitized, null, 2)
      return escapeHtml(truncateLines(json, 200, 4000))
    }
    // it's a string: try to parse JSON
    if (typeof raw === 'string') {
      const trimmed = raw.trim()
      // try parse
      try {
        const parsed = JSON.parse(trimmed)
        const sanitized = sanitizeObject(parsed)
        return escapeHtml(JSON.stringify(sanitized, null, 2))
      } catch {
        // not JSON — mask tokens and truncate
        const masked = maskString(trimmed)
        const txt = truncateLines(masked, 200, 4000)
        return escapeHtml(txt)
      }
    }
    // fallback
    const s = String(raw)
    return escapeHtml(truncateLines(maskString(s), 200, 4000))
  } catch (e) {
    return 'Could not sanitize error.'
  }
}
