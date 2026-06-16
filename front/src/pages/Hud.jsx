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

  const handleWsMessage = useCallback((data) => {
    if (data.type === 'dissonance') {
      store.addDissonance({
        time: data.timestamp,
        value: Math.round(data.value),
        alert_level: data.alert_level,
        face: data.face,
        voice: data.voice,
        quadrant_face: data.quadrant_face,
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

  // Restaurer la position du HUD au chargement
  useEffect(() => {
    if (!electron) return
    const saved = store.getHudBounds()
    if (saved) {
      electron.setBounds(saved)
    }
  }, [electron])

  const handleStart = () => {
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

  const handleTestVibration = (type, intensity) => {
    wsSend({
      type: 'test_vibration',
      test_type: type,
      intensity: intensity,
    })
  }

  const handleStop = () => {
    if (electron) electron.stopSession()
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
            <button className="btn-primary" onClick={handleStart}>
              Démarrer l'assistance
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
