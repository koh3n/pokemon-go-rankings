// Counts which Pokémon get searched, via a tiny Cloudflare Worker (see worker/). Fire-and-forget:
// failures are ignored, and nothing is sent unless VITE_TRACK_URL is set at build time.
const URL_ = import.meta.env.VITE_TRACK_URL as string | undefined

export function trackSearch(text: string) {
  const q = text.trim().toLowerCase().slice(0, 40)
  if (!URL_ || !q || location.hostname === 'localhost') return
  try {
    // text/plain keeps this a "simple" request, so the browser skips the CORS preflight
    fetch(URL_, { method: 'POST', body: q, headers: { 'content-type': 'text/plain' }, keepalive: true }).catch(() => {})
  } catch {
    /* analytics must never break the app */
  }
}
