import { useState, useEffect, useCallback } from 'react'
import { useElectron } from '../hooks/useElectron'
import { useWebSocket } from '../hooks/useWebSocket'
import { useWindowDrag } from '../hooks/useWindowDrag'
import MiniWidget from '../components/MiniWidget'
import SettingsModal from '../components/SettingsModal'
import { store } from '../lib/store'
import { useI18n } from '../lib/i18n'
import '../styles/hud.css'

export default function Hud() {
  const { t } = useI18n()
  const electron = useElectron()
  const drag = useWindowDrag()
  const [phase, setPhase] = useState('waiting') // 'waiting' | 'active'
  const [showSettings, setShowSettings] = useState(false)
  const [hasSensorData, setHasSensorData] = useState(false)
  const [isStarting, setIsStarting] = useState(false)
  const [bleConnected, setBleConnected] = useState(false)
  const [bleLoading, setBleLoading] = useState(false)
  // Dernière mesure reçue, affichée en continu dans le widget. Elle rend
  // l'analyse visible même quand aucune dissonance n'est détectée : sans cela,
  // un système qui fonctionne et ne trouve rien ressemble à un système en panne.
  const [live, setLive] = useState(null)

  const handleWsMessage = useCallback((data) => {
    if (data.type === 'telemetry') {
      setLive(data)
      if (data.face_samples > 0) setHasSensorData(true)
      return
    }
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
      alert(t('backendOffline'))
      return
    }
    setIsStarting(true)
    setPhase('active')
    store.clearDissonances()
    // Trace l'attestation de consentement (voir store.recordConsent).
    store.recordConsent()
    // Purge aussi la mémoire des deux canaux côté moteur : sinon la première
    // fenêtre de la séance est comparée au contexte de la session précédente.
    wsSend({ type: 'reset_context' })
    if (electron) {
      electron.openDashboard()
    }
  }

  // Réinitialise le contexte d'analyse. Utile entre deux séquences de test :
  // sans cela, le premier visage d'une nouvelle vidéo est comparé à la voix de
  // la vidéo précédente encore en mémoire, ce qui produit une fausse dissonance.
  const handleResetContext = () => {
    wsSend({ type: 'reset_context' })
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

  // État de la montre au démarrage, avant toute interaction
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
            {/* La fenêtre est créée non déplaçable par le système : sans cette
                poignée, l'écran de consentement resterait cloué sur place,
                alors que c'est le moment où l'on cadre le HUD sur la visio. */}
            <div
              className="panel-drag"
              title={t('dragWindow')}
              {...drag}
            >
              <span className="panel-grip" />
            </div>
            <h1>{t('consentTitle')}</h1>
            <p>{t('consentBody')}</p>
            <p className="consent-attest">{t('consentAttest')}</p>
            <button
              className="btn-primary"
              onClick={handleStart}
              disabled={isStarting}
            >
              {isStarting ? t('starting') : t('start')}
            </button>
          </div>
        </div>
      )}

      {/* Écran actif */}
      {phase === 'active' && (
        <div className="active-screen">
          <MiniWidget
            live={live}
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
          onResetContext={handleResetContext}
        />
      )}
    </div>
  )
}
