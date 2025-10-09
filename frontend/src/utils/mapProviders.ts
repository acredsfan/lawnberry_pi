export interface LocationLike {
  protocol: string
  hostname: string
}

const PRIVATE_IPV4_REGEX = /^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)/
const LOCAL_SUFFIXES = ['.local', '.lan', '.home', '.internal']

export function isSecureMapsContext(location: LocationLike | null | undefined): boolean {
  if (!location) return false
  const protocol = (location.protocol || '').toLowerCase()
  if (protocol === 'https:') return true

  const host = (location.hostname || '').toLowerCase()
  if (!host) return false
  if (host === 'localhost' || host === '127.0.0.1' || host === '::1') return true
  if (PRIVATE_IPV4_REGEX.test(host)) return true
  if (LOCAL_SUFFIXES.some(suffix => host.endsWith(suffix))) return true
  if (!host.includes('.')) return true
  return false
}

export function shouldUseGoogleProvider(
  provider: string | null | undefined,
  apiKey: string | null | undefined,
  location: LocationLike | null | undefined
): boolean {
  if (provider !== 'google') return false
  if (!apiKey || !apiKey.trim()) return false
  return isSecureMapsContext(location)
}
