import { useCallback, useRef } from 'react'
import { useElectron } from '../hooks/useElectron'

/**
 * Couche invisible pour gérer le drag et le resize de la fenêtre HUD.
 * Utilise les IPC Electron pour déplacer/redimensionner la fenêtre.
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
    electron.setIgnoreMouseEvents(false)
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

    electron.setIgnoreMouseEvents(true, { forward: true })
  }, [electron, onBoundsChange])

  const handlePointerEnter = useCallback(() => {
    if (electron) electron.setIgnoreMouseEvents(false)
  }, [electron])

  const handlePointerLeave = useCallback(() => {
    if (electron && !currentActionRef.current) {
      electron.setIgnoreMouseEvents(true, { forward: true })
    }
  }, [electron])

  // Bordures pour le resize (12px)
  const edges = [
    { cls: 'edge-n', action: 'resize-n', style: { top: 0, left: 12, right: 12, height: 12, cursor: 'ns-resize' } },
    { cls: 'edge-s', action: 'resize-s', style: { bottom: 0, left: 12, right: 12, height: 12, cursor: 'ns-resize' } },
    { cls: 'edge-w', action: 'resize-w', style: { top: 12, bottom: 12, left: 0, width: 12, cursor: 'ew-resize' } },
    { cls: 'edge-e', action: 'resize-e', style: { top: 12, bottom: 12, right: 0, width: 12, cursor: 'ew-resize' } },
    { cls: 'edge-nw', action: 'resize-nw', style: { top: 0, left: 0, width: 20, height: 20, cursor: 'nwse-resize' } },
    { cls: 'edge-ne', action: 'resize-ne', style: { top: 0, right: 0, width: 20, height: 20, cursor: 'nesw-resize' } },
    { cls: 'edge-sw', action: 'resize-sw', style: { bottom: 0, left: 0, width: 20, height: 20, cursor: 'nesw-resize' } },
    { cls: 'edge-se', action: 'resize-se', style: { bottom: 0, right: 0, width: 30, height: 30, cursor: 'nwse-resize' } },
  ]

  // Bordures pour le move (24px)
  const moves = [
    { cls: 'move-n', action: 'move', style: { top: 12, left: 12, right: 12, height: 24, cursor: 'move' } },
    { cls: 'move-s', action: 'move', style: { bottom: 12, left: 12, right: 12, height: 24, cursor: 'move' } },
    { cls: 'move-w', action: 'move', style: { top: 12, bottom: 12, left: 12, width: 24, cursor: 'move' } },
    { cls: 'move-e', action: 'move', style: { top: 12, bottom: 12, right: 12, width: 24, cursor: 'move' } },
  ]

  const baseStyle = {
    position: 'absolute',
    pointerEvents: 'auto',
    backgroundColor: 'rgba(0, 0, 0, 0.01)',
    zIndex: 200,
  }

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 200,
      }}
    >
      {moves.map((m) => (
        <div
          key={m.cls}
          data-action={m.action}
          style={{ ...baseStyle, ...m.style }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerEnter={handlePointerEnter}
          onPointerLeave={handlePointerLeave}
        />
      ))}
      {edges.map((e) => (
        <div
          key={e.cls}
          data-action={e.action}
          style={{ ...baseStyle, ...e.style }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerEnter={handlePointerEnter}
          onPointerLeave={handlePointerLeave}
        />
      ))}
    </div>
  )
}
