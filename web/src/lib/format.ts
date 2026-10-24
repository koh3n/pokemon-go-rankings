/** CSS class for a stat-product percentage: green near the best spread, red when far off. */
export const pctClass = (p: number) => (p >= 98 ? 'pct-hi' : p >= 90 ? 'pct-mid' : 'pct-lo')
