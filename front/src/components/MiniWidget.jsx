import { useRef, useCallback } from 'react'
import Led from './Led'

export default function MiniWidget({ onSettings, onStop, apiStatus, sensorStatus }) {
  const apiColor = apiStatus === 'connected' ? 'green' : 'red'
  const sensorColor = sensorStatus ? 'green' : 'red'
  const draggingRef = useRef(false)
  const startRef = useRef({ x: 0, y: 0 })

  const handlePointerDown = useCallback((e) => {
    if (!window.electronAPI) return
    draggingRef.current = true
    startRef.current = { x: e.screenX, y: e.screenY }
    e.target.setPointerCapture(e.pointerId)
    window.electronAPI.setIgnoreMouseEvents(false)
  }, [])

  const handlePointerMove = useCallback((e) => {
    if (!draggingRef.current || !window.electronAPI) return
    const deltaX = e.screenX - startRef.current.x
    const deltaY = e.screenY - startRef.current.y
    startRef.current = { x: e.screenX, y: e.screenY }
    window.electronAPI.updateWindow('move', deltaX, deltaY)
  }, [])

  const handlePointerUp = useCallback((e) => {
    draggingRef.current = false
    e.target.releasePointerCapture(e.pointerId)
  }, [])

  return (
    <div className="mini-widget glass-panel">
      <div
        className="drag-handle"
        title="Déplacer"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="9" cy="12" r="1" />
          <circle cx="9" cy="5" r="1" />
          <circle cx="9" cy="19" r="1" />
          <circle cx="15" cy="12" r="1" />
          <circle cx="15" cy="5" r="1" />
          <circle cx="15" cy="19" r="1" />
        </svg>
      </div>

      <div style={{ display: 'flex', gap: '12px' }}>
        <Led color={apiColor} label="API" />
        <Led color={sensorColor} label="Capteur" />
      </div>

      <button id="btn-settings" className="icon-btn" onClick={onSettings} title="Paramètres">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      <button className="icon-btn" onClick={onStop} title="Arrêter">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  )
}
