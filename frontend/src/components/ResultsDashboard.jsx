import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  AreaChart, Area,
  ComposedChart, Line, ReferenceArea,
} from 'recharts'

/* ═══════════════════════════════════════════════════════════════════════════
   Design tokens — JP Morgan-inspired dark palette
   ═══════════════════════════════════════════════════════════════════════ */
const T = {
  bg:        '#07070d',
  card:      '#0d0d16',
  cardBorder:'#16162a',
  surface:   '#111122',
  grid:      '#16162a',
  muted:     '#4a4a6a',
  subtle:    '#2a2a44',
  text:      '#e8e8f4',
  textDim:   '#8888aa',
  accent:    '#ff3b5c',
  green:     '#00d4aa',
  font:      "'Space Mono', monospace",
  display:   "'Syne', sans-serif",
}

const BIAS_COLORS = {
  Overtrading:       '#ff3b5c',
  'Loss Aversion':   '#ff9f43',
  'Revenge Trading': '#a855f7',
  FOMO:              '#3b82f6',
  Calm:              '#00d4aa',
}

const BIAS_ICONS = {
  Overtrading:       '\u26a1',
  'Loss Aversion':   '\u{1f6e1}\ufe0f',
  'Revenge Trading': '\u{1f525}',
  FOMO:              '\u{1f4c8}',
  Calm:              '\u2714\ufe0f',
}

const tooltipStyle = {
  background: T.card,
  border: `1px solid ${T.cardBorder}`,
  borderRadius: 10,
  fontFamily: T.font,
  fontSize: 11,
  color: T.text,
  boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
}

const fadeUp = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { type: 'spring', stiffness: 180, damping: 22 },
}

/* ═══════════════════════════════════════════════════════════════════════════
   Card wrapper
   ═══════════════════════════════════════════════════════════════════════ */
function Panel({ children, style, className = '' }) {
  return (
    <div
      className={`rounded-2xl ${className}`}
      style={{
        background: T.card,
        border: `1px solid ${T.cardBorder}`,
        padding: '28px 28px',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

function SectionLabel({ children }) {
  return (
    <h3
      style={{
        fontFamily: T.display,
        fontWeight: 700,
        fontSize: 14,
        color: T.text,
        marginBottom: 4,
        letterSpacing: '0.01em',
      }}
    >
      {children}
    </h3>
  )
}

function SectionCaption({ children }) {
  return (
    <p
      style={{
        fontFamily: T.font,
        fontSize: 11,
        color: T.muted,
        marginBottom: 20,
      }}
    >
      {children}
    </p>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Stat Cards
   ═══════════════════════════════════════════════════════════════════════ */
function StatCard({ label, value, color, subtext }) {
  return (
    <Panel style={{ padding: '22px 24px' }}>
      <p style={{ fontFamily: T.font, fontSize: 10, color: T.muted, textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: 6 }}>
        {label}
      </p>
      <p style={{ fontFamily: T.display, fontWeight: 800, fontSize: 28, color: color || T.text, lineHeight: 1 }}>
        {value}
      </p>
      {subtext && (
        <p style={{ fontFamily: T.font, fontSize: 10, color: T.muted, marginTop: 4 }}>
          {subtext}
        </p>
      )}
    </Panel>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Donut Chart — Bias Distribution
   ═══════════════════════════════════════════════════════════════════════ */
function BiasDistributionPie({ biasCounts, total }) {
  const data = Object.entries(biasCounts)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value, pct: total > 0 ? Math.round((value / total) * 100) : 0 }))

  return (
    <Panel>
      <SectionLabel>Bias Distribution</SectionLabel>
      <SectionCaption>Share of flagged chunks by bias type</SectionCaption>
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={58}
            outerRadius={95}
            paddingAngle={2}
            dataKey="value"
            stroke="none"
          >
            {data.map((e) => (
              <Cell key={e.name} fill={BIAS_COLORS[e.name] || T.muted} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(value, name) => [`${value} chunks`, name]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-x-5 gap-y-2 mt-1 justify-center">
        {data.map((e) => (
          <div key={e.name} className="flex items-center gap-2">
            <span className="inline-block rounded-full" style={{ width: 7, height: 7, background: BIAS_COLORS[e.name] }} />
            <span style={{ fontFamily: T.font, fontSize: 11, color: T.textDim }}>
              {e.name}
            </span>
            <span style={{ fontFamily: T.font, fontSize: 11, color: T.muted }}>
              {e.pct}%
            </span>
          </div>
        ))}
      </div>
    </Panel>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Bar Chart — Bias Frequency
   ═══════════════════════════════════════════════════════════════════════ */
function BiasBarChart({ biasCounts }) {
  const data = Object.entries(biasCounts).map(([name, value]) => ({
    name: name.replace('Trading', 'Trad.'),
    value,
    fill: BIAS_COLORS[name] || T.muted,
  }))

  return (
    <Panel>
      <SectionLabel>Bias Frequency</SectionLabel>
      <SectionCaption>Number of chunks flagged per bias</SectionCaption>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} barSize={28}>
          <CartesianGrid strokeDasharray="3 3" stroke={T.grid} vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: T.muted, fontSize: 10, fontFamily: T.font }}
            axisLine={false}
            tickLine={false}
            interval={0}
            angle={-15}
            textAnchor="end"
            height={50}
          />
          <YAxis
            tick={{ fill: T.muted, fontSize: 10, fontFamily: T.font }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v} chunks`]} cursor={{ fill: 'rgba(255,255,255,0.02)' }} />
          <Bar dataKey="value" radius={[5, 5, 0, 0]}>
            {data.map((e, i) => <Cell key={i} fill={e.fill} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Panel>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Balance Equity Curve with bias-colored sections
   ═══════════════════════════════════════════════════════════════════════ */
function BalanceCurve({ balanceCurve, chunks }) {
  const data = useMemo(() => {
    if (balanceCurve.length <= 2000) return balanceCurve
    const step = Math.ceil(balanceCurve.length / 2000)
    return balanceCurve.filter((_, i) => i % step === 0 || i === balanceCurve.length - 1)
  }, [balanceCurve])

  const sections = useMemo(() => {
    return chunks.map((c) => {
      const s = c.chunk * 10
      const e = Math.min(s + 9, balanceCurve.length - 1)
      return { x1: s, x2: e, color: BIAS_COLORS[c.biases[0]] || T.muted }
    })
  }, [chunks, balanceCurve.length])

  const fmt = (v) => {
    if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`
    if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`
    return `$${v.toFixed(0)}`
  }

  return (
    <Panel>
      <SectionLabel>Equity Curve</SectionLabel>
      <SectionCaption>Balance over time — background tint indicates dominant bias per chunk</SectionCaption>
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={T.grid} vertical={false} />
          {sections.map((s, i) => (
            <ReferenceArea key={i} x1={s.x1} x2={s.x2} fill={s.color} fillOpacity={0.08} strokeOpacity={0} />
          ))}
          <XAxis
            dataKey="trade"
            tick={{ fill: T.muted, fontSize: 10, fontFamily: T.font }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: T.muted, fontSize: 10, fontFamily: T.font }}
            axisLine={false}
            tickLine={false}
            tickFormatter={fmt}
            width={58}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(v) => [`$${Number(v).toLocaleString()}`, 'Balance']}
            labelFormatter={(trade) => {
              const pt = balanceCurve[trade]
              if (!pt) return `Trade #${trade}`
              return `Trade #${trade}  ·  Chunk ${pt.chunk}  ·  ${pt.primary_bias}`
            }}
          />
          <Line
            type="monotone"
            dataKey="balance"
            stroke={T.text}
            strokeWidth={1.4}
            dot={false}
            activeDot={{ r: 3.5, fill: T.accent, stroke: T.accent }}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-x-5 gap-y-2 mt-4 justify-center">
        {Object.entries(BIAS_COLORS).map(([name, color]) => (
          <div key={name} className="flex items-center gap-2">
            <span className="inline-block rounded" style={{ width: 16, height: 7, background: color, opacity: 0.45 }} />
            <span style={{ fontFamily: T.font, fontSize: 10, color: T.muted }}>{name}</span>
          </div>
        ))}
      </div>
    </Panel>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Stacked Area — Bias Timeline
   ═══════════════════════════════════════════════════════════════════════ */
function ChunkTimeline({ chunks }) {
  const data = chunks.map((c) => ({
    chunk: c.chunk,
    Overtrading: c.overtrading ? 1 : 0,
    'Loss Aversion': c.loss_aversion ? 1 : 0,
    'Revenge Trading': c.revenge_trading ? 1 : 0,
    FOMO: c.fomo ? 1 : 0,
  }))
  const keys = ['Overtrading', 'Loss Aversion', 'Revenge Trading', 'FOMO']

  return (
    <Panel>
      <SectionLabel>Bias Heatmap Timeline</SectionLabel>
      <SectionCaption>Stacked detection signals across chunks</SectionCaption>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={T.grid} vertical={false} />
          <XAxis
            dataKey="chunk"
            tick={{ fill: T.muted, fontSize: 10, fontFamily: T.font }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: T.muted, fontSize: 10, fontFamily: T.font }}
            axisLine={false}
            tickLine={false}
            domain={[0, 4]}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(v) => `Chunk ${v}`}
            formatter={(value, name) => [value ? 'Detected' : '-', name]}
          />
          {keys.map((k) => (
            <Area key={k} type="stepAfter" dataKey={k} stackId="1" stroke={BIAS_COLORS[k]} fill={BIAS_COLORS[k]} fillOpacity={0.3} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-x-5 gap-y-2 mt-3 justify-center">
        {keys.map((k) => (
          <div key={k} className="flex items-center gap-2">
            <span className="inline-block rounded-full" style={{ width: 7, height: 7, background: BIAS_COLORS[k] }} />
            <span style={{ fontFamily: T.font, fontSize: 10, color: T.muted }}>{k}</span>
          </div>
        ))}
      </div>
    </Panel>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Chunk Detail Table with reasons
   ═══════════════════════════════════════════════════════════════════════ */
function ChunkTable({ chunks }) {
  const [expanded, setExpanded] = useState(null)

  return (
    <Panel style={{ padding: '28px 0' }}>
      <div style={{ padding: '0 28px', marginBottom: 20 }}>
        <SectionLabel>Chunk-by-Chunk Breakdown</SectionLabel>
        <SectionCaption>Click any row to see why the bias was flagged</SectionCaption>
      </div>
      <div style={{ maxHeight: 440, overflowY: 'auto' }}>
        <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: T.font, fontSize: 11 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '10px 28px', color: T.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.12em', borderBottom: `1px solid ${T.cardBorder}`, position: 'sticky', top: 0, background: T.card, zIndex: 1 }}>
                Chunk
              </th>
              <th style={{ textAlign: 'left', padding: '10px 16px', color: T.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.12em', borderBottom: `1px solid ${T.cardBorder}`, position: 'sticky', top: 0, background: T.card, zIndex: 1 }}>
                Detected Biases
              </th>
              <th style={{ textAlign: 'right', padding: '10px 28px', color: T.muted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.12em', borderBottom: `1px solid ${T.cardBorder}`, position: 'sticky', top: 0, background: T.card, zIndex: 1 }}>
                Signals
              </th>
            </tr>
          </thead>
          <tbody>
            {chunks.map((c) => {
              const isOpen = expanded === c.chunk
              const hasReasons = c.reasons && c.reasons.length > 0
              return (
                <motion.tr
                  key={c.chunk}
                  onClick={() => setExpanded(isOpen ? null : c.chunk)}
                  style={{
                    cursor: hasReasons ? 'pointer' : 'default',
                    background: isOpen ? T.surface : 'transparent',
                    transition: 'background 0.15s',
                  }}
                  whileHover={{ background: T.surface }}
                >
                  <td style={{ padding: '12px 28px', color: T.text, borderBottom: `1px solid ${T.cardBorder}`, verticalAlign: 'top' }}>
                    <span style={{ fontWeight: 600 }}>{c.chunk}</span>
                  </td>
                  <td style={{ padding: '12px 16px', borderBottom: `1px solid ${T.cardBorder}`, verticalAlign: 'top' }}>
                    <div className="flex flex-wrap gap-1.5">
                      {c.biases.map((b) => (
                        <span
                          key={b}
                          className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5"
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            background: `${BIAS_COLORS[b] || T.muted}15`,
                            color: BIAS_COLORS[b] || T.muted,
                            border: `1px solid ${BIAS_COLORS[b] || T.muted}30`,
                          }}
                        >
                          {b}
                        </span>
                      ))}
                    </div>
                    {/* Expanded reasons */}
                    <AnimatePresence>
                      {isOpen && hasReasons && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          style={{ overflow: 'hidden' }}
                        >
                          <div style={{ paddingTop: 10 }}>
                            {c.reasons.map((r, i) => (
                              <div
                                key={i}
                                className="flex items-start gap-2"
                                style={{ padding: '3px 0', color: T.textDim, fontSize: 10 }}
                              >
                                <span style={{ color: T.accent, flexShrink: 0, marginTop: 1 }}>
                                  \u25B8
                                </span>
                                {r}
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </td>
                  <td style={{ padding: '12px 28px', borderBottom: `1px solid ${T.cardBorder}`, textAlign: 'right', color: T.muted, verticalAlign: 'top' }}>
                    {c.reasons ? c.reasons.length : 0}
                  </td>
                </motion.tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Main Dashboard
   ═══════════════════════════════════════════════════════════════════════ */
export default function ResultsDashboard({ result, onBack }) {
  const { total_chunks, bias_counts, chunks, balance_curve, filename, clean_rows, sensitivity, max_gap } = result

  const biasedChunks = total_chunks - (bias_counts.Calm || 0)
  const biasRate = total_chunks > 0 ? Math.round((biasedChunks / total_chunks) * 100) : 0

  // Dominant bias
  const dominant = Object.entries(bias_counts)
    .filter(([k]) => k !== 'Calm')
    .sort((a, b) => b[1] - a[1])[0]
  const dominantName = dominant && dominant[1] > 0 ? dominant[0] : 'None'

  return (
    <div style={{ background: T.bg, minHeight: '100vh' }}>
      <div
        className="mx-auto px-4 sm:px-6 py-12"
        style={{ maxWidth: 1040 }}
      >

        {/* ── Top bar ───────────────────────────────────────────────── */}
        <motion.div className="flex items-center justify-between mb-10" {...fadeUp}>
          <button
            onClick={onBack}
            className="flex items-center gap-2 transition-colors"
            style={{ fontFamily: T.font, fontSize: 11, color: T.muted }}
            onMouseEnter={(e) => (e.currentTarget.style.color = T.accent)}
            onMouseLeave={(e) => (e.currentTarget.style.color = T.muted)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            New Analysis
          </button>
          <span style={{ fontFamily: T.font, fontSize: 10, color: T.muted, textTransform: 'uppercase', letterSpacing: '0.15em' }}>
            Bias Detection Engine
          </span>
        </motion.div>

        {/* ── Header ────────────────────────────────────────────────── */}
        <motion.header className="mb-10" {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.03 }}>
          <h1
            style={{
              fontFamily: T.display,
              fontWeight: 800,
              fontSize: 'clamp(1.6rem, 4vw, 2.4rem)',
              color: T.text,
              lineHeight: 1.1,
              marginBottom: 8,
            }}
          >
            {filename}
          </h1>
          <div className="flex flex-wrap gap-x-4 gap-y-1" style={{ fontFamily: T.font, fontSize: 11, color: T.muted }}>
            <span>{clean_rows.toLocaleString()} trades analysed</span>
            <span style={{ color: T.subtle }}>|</span>
            <span>Sensitivity {sensitivity}</span>
            <span style={{ color: T.subtle }}>|</span>
            <span>Max gap {max_gap}</span>
            <span style={{ color: T.subtle }}>|</span>
            <span>Dominant: <span style={{ color: BIAS_COLORS[dominantName] || T.muted, fontWeight: 700 }}>{dominantName}</span></span>
          </div>
        </motion.header>

        {/* ── Stat Cards ────────────────────────────────────────────── */}
        <motion.div
          className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8"
          {...fadeUp}
          transition={{ ...fadeUp.transition, delay: 0.06 }}
        >
          <StatCard label="Total Chunks" value={total_chunks} subtext="10 trades each" />
          <StatCard label="Biased" value={biasedChunks} color={T.accent} subtext={`${biasRate}% of total`} />
          <StatCard label="Calm" value={bias_counts.Calm || 0} color={T.green} subtext={`${total_chunks > 0 ? 100 - biasRate : 0}% of total`} />
          <StatCard label="Bias Rate" value={`${biasRate}%`} color={biasRate > 50 ? T.accent : T.green} subtext={biasRate > 50 ? 'High risk' : 'Moderate'} />
        </motion.div>

        {/* ── Pie + Bar ─────────────────────────────────────────────── */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-8"
          {...fadeUp}
          transition={{ ...fadeUp.transition, delay: 0.09 }}
        >
          <BiasDistributionPie biasCounts={bias_counts} total={total_chunks} />
          <BiasBarChart biasCounts={bias_counts} />
        </motion.div>

        {/* ── Balance Curve ─────────────────────────────────────────── */}
        {balance_curve && balance_curve.length > 0 && (
          <motion.div className="mb-8" {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.12 }}>
            <BalanceCurve balanceCurve={balance_curve} chunks={chunks} />
          </motion.div>
        )}

        {/* ── Timeline ──────────────────────────────────────────────── */}
        <motion.div className="mb-8" {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.15 }}>
          <ChunkTimeline chunks={chunks} />
        </motion.div>

        {/* ── Chunk Table ───────────────────────────────────────────── */}
        <motion.div className="mb-20" {...fadeUp} transition={{ ...fadeUp.transition, delay: 0.18 }}>
          <ChunkTable chunks={chunks} />
        </motion.div>

      </div>
    </div>
  )
}
