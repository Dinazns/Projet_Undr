import { useState } from 'react'
import { useAudioDevices } from '../hooks/useAudioDevices'
import { LANGS, useI18n } from '../lib/i18n'

export default function SettingsModal({ onClose, onTestVibration, onResetContext }) {
  const { lang, setLang, t } = useI18n()
  const {
    devices,
    current,
    defaultSpeaker,
    loading,
    error,
    refresh,
    testDevice,
    selectDevice,
  } = useAudioDevices()

  const [selected, setSelected] = useState(current || '')
  const [testing, setTesting] = useState(false)
  const [level, setLevel] = useState(null) // énergie 0..1
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [contextReset, setContextReset] = useState(false)

  const handleResetContext = () => {
    if (!onResetContext) return
    onResetContext()
    setContextReset(true)
    setTimeout(() => setContextReset(false), 2000)
  }

  const handleTest = async () => {
    const deviceId = selected || defaultSpeaker
    if (!deviceId) return
    setTesting(true)
    setLevel(null)
    try {
      const data = await testDevice(deviceId, 1.5)
      setLevel(data.energy)
    } catch (e) {
      setLevel(-1)
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await selectDevice(selected || null)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } finally {
      setSaving(false)
    }
  }

  const levelPercent = level == null ? 0 : Math.max(0, Math.min(100, level * 100 * 4))
  const levelColor =
    level == null
      ? 'rgba(255,255,255,0.25)'
      : level < 0
      ? '#ff5c5c'
      : level > 0.001
      ? '#9eff9e'
      : '#ffb347'

  return (
    <div className="settings-overlay">
      <div className="settings-panel glass-panel">
        <h2>{t('settings')}</h2>

        {/* --- Langue de l'interface --- */}
        <div className="settings-section">
          <h3>{t('language')}</h3>
          <p className="settings-hint">{t('languageHint')}</p>
          <select
            className="settings-select"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
          >
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </div>

        {/* --- Périphérique audio --- */}
        <div className="settings-section">
          <h3>{t('audioSection')}</h3>
          <p className="settings-hint">{t('audioHint')}</p>

          {error && <p className="settings-error">{error}</p>}

          <label className="settings-label">{t('device')}</label>
          <select
            className="settings-select"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={loading}
          >
            <option value="">
              {t('defaultSpeaker')} {defaultSpeaker ? `(${defaultSpeaker})` : ''}
            </option>
            {devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>

          <div className="audio-test-row">
            <button
              className="btn-outline"
              onClick={handleTest}
              disabled={testing || loading}
            >
              {testing ? t('measuring') : t('testSound')}
            </button>

            <div className="audio-level-bar">
              <div
                className="audio-level-fill"
                style={{
                  width: `${levelPercent}%`,
                  backgroundColor: levelColor,
                }}
              />
            </div>
          </div>

          {level != null && (
            <p className="audio-level-text" style={{ color: levelColor }}>
              {level < 0
                ? t('captureError')
                : level > 0.001
                ? t('soundDetected', { level: Math.round(level * 1000) / 10 })
                : t('noSound')}
            </p>
          )}

          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={saving}
            style={saved ? { backgroundColor: 'rgba(222,255,154,0.5)' } : {}}
          >
            {saved ? t('saved') : saving ? t('saving') : t('saveChoice')}
          </button>
        </div>

        {/* --- Contexte d'analyse --- */}
        <div className="settings-section">
          <h3>{t('contextSection')}</h3>
          <p className="settings-hint">{t('contextHint')}</p>
          <button
            className="btn-outline"
            onClick={handleResetContext}
            style={contextReset ? { backgroundColor: 'rgba(222,255,154,0.5)' } : {}}
          >
            {contextReset ? t('contextReset') : t('resetContext')}
          </button>
        </div>

        {/* --- Test bracelet --- */}
        <div className="settings-section">
          <h3>{t('braceletSection')}</h3>
          <div className="settings-actions">
            <button
              className="btn-test-severe"
              onClick={() => onTestVibration('severe')}
            >
              {t('testSevere')}
            </button>
            <button
              className="btn-test-vigilance"
              onClick={() => onTestVibration('vigilance')}
            >
              {t('testVigilance')}
            </button>
          </div>
        </div>

        <button className="btn-outline" onClick={onClose}>
          {t('close')}
        </button>
      </div>
    </div>
  )
}
