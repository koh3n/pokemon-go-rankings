// Counts Pokémon searches in Workers Analytics Engine. One data point per search:
// blob1 = lowercase search text. Query it with the Analytics Engine SQL API (see README).
const ORIGINS = ['https://mooplyn.com']

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin')
    const cors = { 'access-control-allow-origin': ORIGINS.includes(origin) ? origin : ORIGINS[0] }
    if (request.method !== 'POST' || !ORIGINS.includes(origin)) return new Response(null, { status: 204, headers: cors })
    const q = (await request.text()).trim().toLowerCase().slice(0, 40)
    if (q) env.SEARCHES.writeDataPoint({ blobs: [q], doubles: [1], indexes: [q] })
    return new Response(null, { status: 204, headers: cors })
  },
}
