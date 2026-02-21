import { motion } from 'framer-motion'
import { Card } from './ui/card'
import { Separator } from './ui/separator'

function FileIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#5a5a7a" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  )
}

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(1)} KB`
}

export default function FilePreview({ file, rowCount, onClear }) {
  if (!file) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 12 }}
      transition={{ type: 'spring', stiffness: 280, damping: 24 }}
    >
      <Card className="relative">
        {/* Clear button */}
        <button
          onClick={onClear}
          className="absolute top-4 right-4 font-mono text-sm leading-none transition-colors"
          style={{ color: '#5a5a7a' }}
          onMouseEnter={(e) => (e.target.style.color = '#ff3b5c')}
          onMouseLeave={(e) => (e.target.style.color = '#5a5a7a')}
          aria-label="Clear file"
        >
          ×
        </button>

        {/* Top row: icon + name + badges */}
        <div className="flex items-center justify-between gap-4 pr-6">
          {/* Left: icon + file info */}
          <div className="flex items-center gap-3 min-w-0">
            <FileIcon />
            <div className="min-w-0">
              <p
                className="font-syne font-semibold text-sm truncate"
                style={{ color: '#e2e2f0' }}
              >
                {file.name}
              </p>
              <p className="font-mono text-xs mt-0.5" style={{ color: '#5a5a7a' }}>
                {formatSize(file.size)}
              </p>
            </div>
          </div>

          {/* Right: stat pills */}
          <div className="flex items-center gap-2 shrink-0">
            <span
              className="font-mono text-xs px-2 py-0.5 rounded-md"
              style={{ background: 'rgba(0,212,170,0.1)', color: '#00d4aa', border: '1px solid rgba(0,212,170,0.2)' }}
            >
              {rowCount.toLocaleString()} rows
            </span>
            <span
              className="font-mono text-xs px-2 py-0.5 rounded-md"
              style={{ background: '#1e1e2e', color: '#5a5a7a', border: '1px solid #1e1e2e' }}
            >
              CSV
            </span>
          </div>
        </div>

        <Separator className="my-4" />

        {/* Footer line */}
        <p className="font-mono text-xs" style={{ color: '#5a5a7a' }}>
          Ready for analysis · overtrader + fomo_trader detectors
        </p>
      </Card>
    </motion.div>
  )
}
