import { useState, useEffect, useCallback } from 'react'
import { useElectron } from '../hooks/useElectron'
import { useWebSocket } from '../hooks/useWebSocket'
import MiniWidget from '../components/MiniWidget'
import SettingsModal from '../components/SettingsModal'
import { store } from '../lib/store'
import '../styles/hud.css'

export default function Hud() {
  const electron = useElectron()
  const [phase, setPhase] = useState('waiting') // 'waiting' | 'active'
  const [showSettings, setShowSettings] = useState(false)
  const [hasSensorData, setHasSensorData] = useState(false)
  const [isStarting, setIsStarting] = useState(false)
  const [bleConnected, setBleConnected] = useState(false)
  const [bleLoading, setBleLoading] = useState(false)

  const handleWsMessage = useCallback((data) => {
    if (data.type === 'dissonance') {
      store.addDissonance({
        time: data.timestamp,
        value: Math.round(data.value),
        alert_level: data.alert_level,
        face: data.face,
        voice: data.voice,
        quadrant_face: data.quadrant_face,
        quadrant_voice: data.quadrant_voice,
        face_coords: data.face_coords || null,
        voice_coords: data.voice_coords || null,
        emotion_distance: data.emotion_distance,
      })
      setHasSensorData(true)
    }
  }, [])

  const { status: wsStatus, send: wsSend } = useWebSocket(handleWsMessage)

  // Envoyer les bounds au back régulièrement
  useEffect(() => {
    if (phase !== 'active' || !electron) return

    const interval = setInterval(() => {
      electron.getBounds().then((bounds) => {
        wsSend(bounds)
      })
    }, 500)

    return () => clearInterval(interval)
  }, [phase, electron, wsSend])

  // Fermer la modal avec Escape
  useEffect(() => {
    if (!showSettings) return
    const handleKey = (e) => {
      if (e.key === 'Escape') setShowSettings(false)
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [showSettings])

  const handleStart = () => {
    if (isStarting) return
    if (wsStatus !== 'connected') {
      alert("Le moteur d'analyse n'est pas connecté. Veuillez démarrer le backend.")
      return
    }
    setIsStarting(true)
    setPhase('active')
    store.clearDissonances()
    if (electron) {
      electron.openDashboard()
    }
  }

  const handleSettingsOpen = () => {
    setShowSettings(true)
  }

  const handleSettingsClose = () => {
    setShowSettings(false)
  }

  const handleTestVibration = (type) => {
    wsSend({
      type: 'test_vibration',
      test_type: type,
    })
  }

  const handleStop = () => {
    if (electron) electron.stopSession()
  }

  // Check initial BLE status
  useEffect(() => {
    if (electron) {
      electron.getBLEStatus().then(data => {
        setBleConnected(data.ble_connected)
      })
    }
  }, [electron])

  const handleConnectBLE = async () => {
    if (!electron || bleLoading) return
    setBleLoading(true)
    try {
      const data = await electron.connectBLE()
      setBleConnected(data.ble_connected)
    } catch (e) {
      console.error('Erreur connexion BLE:', e)
    } finally {
      setBleLoading(false)
    }
  }

  const handleDisconnectBLE = async () => {
    if (!electron || bleLoading) return
    setBleLoading(true)
    try {
      const data = await electron.disconnectBLE()
      setBleConnected(data.ble_connected)
    } catch (e) {
      console.error('Erreur déconnexion BLE:', e)
    } finally {
      setBleLoading(false)
    }
  }

  return (
    <div className={`hud-container ${phase === 'active' ? 'hud-active' : ''}`}>
      {/* Cadre de capture */}
      <div className="capture-frame" />

      {/* Écran d'attente */}
      {phase === 'waiting' && (
        <div className="waiting-screen">
          <div className="glass-panel main-panel">
            <h1>Consentement requis</h1>
            <p>L'assistant analysera les émotions dans ce cadre.</p>
            <button
              className="btn-primary"
              onClick={handleStart}
              disabled={isStarting}
            >
              {isStarting ? 'Démarrage...' : 'Démarrer l\'assistance'}
            </button>
          </div>
        </div>
      )}

      {/* Écran actif */}
      {phase === 'active' && (
        <div className="active-screen">
          <MiniWidget
            apiStatus={wsStatus}
            sensorStatus={hasSensorData}
            bleStatus={bleConnected}
            bleLoading={bleLoading}
            onConnectBLE={handleConnectBLE}
            onDisconnectBLE={handleDisconnectBLE}
            onSettings={handleSettingsOpen}
            onStop={handleStop}
          />
        </div>
      )}

      {/* Modal paramètres */}
      {showSettings && (
        <SettingsModal
          onClose={handleSettingsClose}
          onTestVibration={handleTestVibration}
        />
      )}
    </div>
  )
}
