import { useEffect, useRef, useState, useCallback } from 'react'
import { WS_URL } from '../lib/constants'

/**
 * Hook React pour gérer la connexion WebSocket au back FastAPI.
 * Gère la reconnexion automatique en cas de déconnexion.
 */
export function useWebSocket(onMessage) {
  const wsRef = useRef(null)
  const [status, setStatus] = useState('disconnected') // 'connected' | 'disconnected' | 'connecting'
  const reconnectTimeoutRef = useRef(null)

  const connect = useCallback(() => {
    setStatus('connecting')

    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        console.log('WebSocket connecté au moteur Python')
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (onMessage) onMessage(data)
        } catch (e) {
          console.error('Erreur de parsing du message WS:', e)
        }
      }

      ws.onerror = (err) => {
        console.error('Erreur WebSocket:', err)
        setStatus('disconnected')
      }

      ws.onclose = () => {
        setStatus('disconnected')
        wsRef.current = null

        // Reconnexion automatique après 2 secondes
        reconnectTimeoutRef.current = setTimeout(() => {
          connect()
        }, 2000)
      }
    } catch (e) {
      console.error('Impossible de créer le WebSocket:', e)
      setStatus('disconnected')
    }
  }, [onMessage])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const send = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { status, send, disconnect }
}
