import { useState, useEffect, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import Papa from 'papaparse'
import { motion, AnimatePresence } from 'framer-motion'

// ── inline SVG icons ────────────────────────────────────────────────────────

function UploadIcon({ color }) {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 16 12 12 8 16" />
      <line x1="12" y1="12" x2="12" y2="21" />
      <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#00d4aa" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

// ── zone states ──────────────────────────────────────────────────────────────

const STATES = {
  IDLE:     'idle',
  DRAG:     'drag',
  ACCEPTED: 'accepted',
  REJECTED: 'rejected',
}

const zoneStyle = {
  [STATES.IDLE]: {
    border: '1.5px dashed #1e1e2e',
    background: '#15151f',
    scale: 1,
  },
  [STATES.DRAG]: {
    border: '1.5px dashed #ff3b5c',
    background: 'rgba(255,59,92,0.05)',
    scale: 1.01,
  },
  [STATES.ACCEPTED]: {
    border: '1.5px solid #00d4aa',
    background: 'rgba(0,212,170,0.05)',
    scale: 1,
  },
  [STATES.REJECTED]: {
    border: '1.5px dashed #ff3b5c',
    background: 'rgba(255,59,92,0.05)',
    scale: 1,
  },
}

// ─────────────────────────────────────────────────────────────────────────────

export default function UploadZone({ onFileAccepted, onFileRejected }) {
  const [zoneState, setZoneState] = useState(STATES.IDLE)

  // Auto-reset rejected state after 3 s
  useEffect(() => {
    if (zoneState !== STATES.REJECTED) return
    const t = setTimeout(() => setZoneState(STATES.IDLE), 3000)
    return () => clearTimeout(t)
  }, [zoneState])

  const onDrop = useCallback((accepted, rejected) => {
    if (rejected.length > 0) {
      setZoneState(STATES.REJECTED)
      onFileRejected?.()
      return
    }
    if (accepted.length === 0) return

    const file = accepted[0]
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        setZoneState(STATES.ACCEPTED)
        onFileAccepted(file, results.data)
      },
    })
  }, [onFileAccepted, onFileRejected])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'text/csv': ['.csv'] },
    multiple: false,
  })

  // Sync drag state
  const currentState = isDragActive
    ? STATES.DRAG
    : zoneState

  const style = zoneStyle[currentState]

  return (
    <motion.div
      {...getRootProps()}
      animate={{ scale: style.scale }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      className="relative flex flex-col items-center justify-center rounded-xl cursor-pointer min-h-[220px] select-none outline-none"
      style={{ border: style.border, background: style.background, transition: 'border-color 0.2s, background 0.2s' }}
    >
      <input {...getInputProps()} />

      <AnimatePresence mode="wait">
        {currentState === STATES.ACCEPTED ? (
          <motion.div
            key="accepted"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="flex flex-col items-center gap-3"
          >
            <CheckIcon />
            <span className="font-syne font-medium text-base" style={{ color: '#00d4aa' }}>
              File loaded
            </span>
          </motion.div>
        ) : currentState === STATES.REJECTED ? (
          <motion.div
            key="rejected"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="flex flex-col items-center gap-3"
          >
            <UploadIcon color="#ff3b5c" />
            <span className="font-mono text-sm" style={{ color: '#ff3b5c' }}>
              Only CSV files are supported
            </span>
          </motion.div>
        ) : currentState === STATES.DRAG ? (
          <motion.div
            key="drag"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="flex flex-col items-center gap-3"
          >
            <UploadIcon color="#ff3b5c" />
            <span className="font-syne font-medium text-base" style={{ color: '#ff3b5c' }}>
              Release to upload
            </span>
          </motion.div>
        ) : (
          <motion.div
            key="idle"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="flex flex-col items-center gap-3"
          >
            <UploadIcon color="#5a5a7a" />
            <div className="flex flex-col items-center gap-1">
              <span className="font-syne font-medium text-base" style={{ color: '#e2e2f0' }}>
                Drop your CSV here
              </span>
              <span className="font-mono text-xs" style={{ color: '#5a5a7a' }}>
                or click to browse
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
