import { useState, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import UploadZone from './components/UploadZone'
import FilePreview from './components/FilePreview'
import AnalyseButton from './components/AnalyseButton'
import { useUpload } from './hooks/useUpload'

export default function App() {
  const [file, setFile]             = useState(null)
  const [parsedRows, setParsedRows] = useState([])
  const [visibleError, setVisibleError] = useState(null)

  const { upload, isLoading, error, result } = useUpload()

  useEffect(() => {
    if (!error) return
    setVisibleError(error)
    const t = setTimeout(() => setVisibleError(null), 6000)
    return () => clearTimeout(t)
  }, [error])

  useEffect(() => {
    if (result) console.log('[Upload result]', result)
  }, [result])

  function handleFileAccepted(acceptedFile, rows) {
    setFile(acceptedFile)
    setParsedRows(rows)
    setVisibleError(null)
  }

  function handleClear() {
    setFile(null)
    setParsedRows([])
    setVisibleError(null)
  }

  async function handleUpload() {
    if (!file) return
    await upload(file)
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-start py-16 px-4"
      style={{ background: '#0a0a0f' }}
    >
      <div className="w-full" style={{ maxWidth: 680 }}>

        {/* ── Header ──────────────────────────────────────────────────────── */}
        <header className="mb-10">
          <p
            className="font-mono text-xs tracking-[0.2em] uppercase mb-4"
            style={{ color: '#ff3b5c' }}
          >
            Bias Detection Engine
          </p>
          <h1
            className="font-syne font-extrabold mb-3"
            style={{ fontSize: 'clamp(1.75rem, 5vw, 2.5rem)', color: '#e2e2f0', lineHeight: 1.1 }}
          >
            Upload Trading Session
          </h1>
          <p className="font-mono text-xs leading-relaxed" style={{ color: '#5a5a7a' }}>
            Supports CSV exports with timestamp, asset, side, quantity,<br className="hidden sm:block" />
            entry_price, exit_price, profit_loss, balance columns
          </p>
        </header>

        {/* ── Upload Zone ─────────────────────────────────────────────────── */}
        <UploadZone
          onFileAccepted={handleFileAccepted}
          onFileRejected={() => {}}
        />

        {/* ── File Preview ────────────────────────────────────────────────── */}
        <AnimatePresence>
          {file && (
            <div className="mt-4">
              <FilePreview
                file={file}
                rowCount={parsedRows.length}
                onClear={handleClear}
              />
            </div>
          )}
        </AnimatePresence>

        {/* ── Upload Button ───────────────────────────────────────────────── */}
        <div className="mt-4">
          <AnalyseButton
            onClick={handleUpload}
            isLoading={isLoading}
            disabled={!file}
          />
        </div>

        {/* ── Error Banner ────────────────────────────────────────────────── */}
        <AnimatePresence>
          {visibleError && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              transition={{ type: 'spring', stiffness: 280, damping: 24 }}
              className="mt-4 rounded-xl px-5 py-4 font-mono text-xs"
              style={{
                background: 'rgba(255,59,92,0.08)',
                border: '1px solid rgba(255,59,92,0.25)',
                color: '#ff3b5c',
              }}
            >
              {visibleError}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Success Banner ──────────────────────────────────────────────── */}
        <AnimatePresence>
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              transition={{ type: 'spring', stiffness: 280, damping: 24 }}
              className="mt-4 rounded-xl px-5 py-4 font-mono text-xs"
              style={{
                background: 'rgba(0,212,170,0.08)',
                border: '1px solid rgba(0,212,170,0.2)',
                color: '#00d4aa',
              }}
            >
              {result.message}
              {result.original_rows !== result.clean_rows && (
                <span className="ml-2" style={{ color: '#00a882' }}>
                  ({result.original_rows - result.clean_rows} row(s) removed during cleaning)
                </span>
              )}
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </div>
  )
}
