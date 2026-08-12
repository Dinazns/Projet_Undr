import { useCallback, useRef } from 'react'

/**
 * Rend une zone de l'interface saisissable pour déplacer la fenêtre HUD.
 *
 * La fenêtre est créée avec `setMovable(false)` côté Electron, car un HUD
 * transparent sans cadre n'offre aucune barre de titre à saisir. Le
 * déplacement passe donc obligatoirement par une poignée applicative, qui
 * envoie ses deltas au processus principal.
 *
 * Le hook existe pour que cette poignée puisse être posée partout où l'on en a
 * besoin. Tant qu'elle n'existait que dans le widget de la phase active,
 * l'écran de consentement était impossible à déplacer, alors que c'est
 * justement le moment où le praticien cherche à cadrer sa fenêtre sur la visio.
 *
 * Renvoie les trois gestionnaires à étaler sur l'élément saisissable.
 */
export function useWindowDrag() {
  const dragging = useRef(false)
  const origin = useRef({ x: 0, y: 0 })

  const onPointerDown = useCallback((e) => {
    if (!window.electronAPI) return
    dragging.current = true
    origin.current = { x: e.screenX, y: e.screenY }
    // La capture est posée sur la poignée elle-même : sans elle, un
    // déplacement rapide sort du curseur de l'élément et le glissement casse.
    e.currentTarget.setPointerCapture(e.pointerId)
    window.electronAPI.setIgnoreMouseEvents(false)
  }, [])

  const onPointerMove = useCallback((e) => {
    if (!dragging.current || !window.electronAPI) return
    const deltaX = e.screenX - origin.current.x
    const deltaY = e.screenY - origin.current.y
    origin.current = { x: e.screenX, y: e.screenY }
    window.electronAPI.updateWindow('move', deltaX, deltaY)
  }, [])

  const onPointerUp = useCallback((e) => {
    dragging.current = false
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // Le pointeur a pu être relâché hors de l'élément : sans conséquence.
    }
  }, [])

  return { onPointerDown, onPointerMove, onPointerUp }
}
