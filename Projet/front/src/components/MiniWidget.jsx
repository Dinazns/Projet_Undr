import Led from './Led'
import { useWindowDrag } from '../hooks/useWindowDrag'
import { translateEmotion, translateSkipped, useI18n } from '../lib/i18n'

const NIVEAU_COULEUR = {
  SEVERE: '#ff5c5c',
  MODERATE: '#ffa500',
  VIGILANCE: '#ffff00',
  NONE: 'rgba(222, 255, 154, 0.7)',
}

// Borne d'affichage de la jauge. La distance maximale théorique dans le plan de
// Russell vaut environ 2,83 ; en pratique elle dépasse rarement 1,6.
const DISTANCE_MAX_AFFICHEE = 1.6

export default function MiniWidget({ 
    live,
    onSettings, 
    onStop, 
    apiStatus, 
    sensorStatus, 
    bleStatus,
    bleLoading,
    onConnectBLE,
    onDisconnectBLE,
  }) {
  const { lang, t } = useI18n()
  const apiColor = apiStatus === 'connected' ? 'green' : 'red'
  const sensorColor = sensorStatus ? 'green' : 'red'
  const bleColor = bleStatus ? 'green' : 'red'
  const drag = useWindowDrag()

  return (
    <div className="mini-widget glass-panel">
      <div className="drag-handle" title={t('move')} {...drag}>
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
        <Led color={sensorColor} label={t('ledSensor')} />
        <Led color={bleColor} label="BLE" />
      </div>

      {/* Mesure en direct : visible à chaque fenêtre, même sans alerte. */}
      <div className="live-readout" title={t('gaugeTitle')}>
        <div className="live-gauge">
          <div
            className="live-gauge-fill"
            style={{
              width: `${Math.min(100, ((live?.distance ?? 0) / DISTANCE_MAX_AFFICHEE) * 100)}%`,
              backgroundColor: NIVEAU_COULEUR[live?.alert_level] || NIVEAU_COULEUR.NONE,
            }}
          />
        </div>
        <span className="live-label">
          {live
            ? (live.skipped
                ? translateSkipped(live.skipped, lang)
                : `${translateEmotion(live.face, lang) || '—'} / ${translateEmotion(live.voice, lang) || '—'} · ${live.distance?.toFixed(2)}`)
            : t('waiting')}
        </span>
      </div>

      <button 
        className="icon-btn" 
        onClick={bleStatus ? onDisconnectBLE : onConnectBLE} 
        title={bleStatus ? t('disconnectWatch') : t('connectWatch')}
        disabled={bleLoading}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {bleStatus ? (
            <path d="M18 6L6 18M6 6l12 12" />
          ) : (
            <path d="M7 7l10 10-5 5V2L17 9l-5 5" />
          )}
        </svg>
      </button>

      <button id="btn-settings" className="icon-btn" onClick={onSettings} title={t('settings')}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      <button className="icon-btn" onClick={onStop} title={t('stop')}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  )
}
