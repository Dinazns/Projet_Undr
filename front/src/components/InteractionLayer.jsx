import { useCallback, useRef } from 'react'
import { useElectron } from '../hooks/useElectron'

/**
 * Couche invisible pour gérer le resize de la fenêtre HUD.
 * Le drag est géré par le MiniWidget. Utilise les IPC Electron.
 */
export default function InteractionLayer({ onBoundsChange }) {
  const electron = useElectron()
  const currentActionRef = useRef(null)
  const startRef = useRef({ x: 0, y: 0 })

  const handlePointerDown = useCallback((e) => {
    if (!electron) return
    const action = e.target.dataset.action
    if (!action) return

    currentActionRef.current = action
    startRef.current = { x: e.screenX, y: e.screenY }
    e.target.setPointerCapture(e.pointerId)
  }, [electron])

  const handlePointerMove = useCallback((e) => {
    if (!electron || !currentActionRef.current) return

    const deltaX = e.screenX - startRef.current.x
    const deltaY = e.screenY - startRef.current.y
    startRef.current = { x: e.screenX, y: e.screenY }

    electron.updateWindow(currentActionRef.current, deltaX, deltaY)
  }, [electron])

  const handlePointerUp = useCallback((e) => {
    if (!electron || !currentActionRef.current) return

    currentActionRef.current = null
    e.target.releasePointerCapture(e.pointerId)

    electron.getBounds().then((bounds) => {
      onBoundsChange(bounds)
    })
  }, [electron, onBoundsChange])

  // Bordures pour le resize (16px pour etre faciles a attraper)
  const edges = [
    { cls: 'edge-n', action: 'resize-n', style: { top: 0, left: 24, right: 24, height: 16, cursor: 'ns-resize' } },
    { cls: 'edge-s', action: 'resize-s', style: { bottom: 0, left: 24, right: 24, height: 16, cursor: 'ns-resize' } },
    { cls: 'edge-w', action: 'resize-w', style: { top: 24, bottom: 24, left: 0, width: 16, cursor: 'ew-resize' } },
    { cls: 'edge-e', action: 'resize-e', style: { top: 24, bottom: 24, right: 0, width: 16, cursor: 'ew-resize' } },
    { cls: 'edge-nw', action: 'resize-nw', style: { top: 0, left: 0, width: 28, height: 28, cursor: 'nwse-resize' } },
    { cls: 'edge-ne', action: 'resize-ne', style: { top: 0, right: 0, width: 28, height: 28, cursor: 'nesw-resize' } },
    { cls: 'edge-sw', action: 'resize-sw', style: { bottom: 0, left: 0, width: 28, height: 28, cursor: 'nesw-resize' } },
    { cls: 'edge-se', action: 'resize-se', style: { bottom: 0, right: 0, width: 32, height: 32, cursor: 'nwse-resize' } },
  ]

  const baseStyle = {
    position: 'absolute',
    pointerEvents: 'auto',
    backgroundColor: 'rgba(0, 0, 0, 0.01)',
    zIndex: 150,
  }

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 150,
      }}
    >
      {edges.map((e) => (
        <div
          key={e.cls}
          data-action={e.action}
          style={{ ...baseStyle, ...e.style }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        />
      ))}
    </div>
  )
}
