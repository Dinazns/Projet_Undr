import { useState } from 'react'
import { useAudioDevices } from '../hooks/useAudioDevices'

export default function SettingsModal({ onClose, onTestVibration }) {
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
        <h2>Paramètres</h2>

        {/* --- Périphérique audio --- */}
        <div className="settings-section">
          <h3>Capture Audio (Voix)</h3>
          <p className="settings-hint">
            Choisissez la sortie audio à intercepter (loopback). Testez le niveau
            pour vérifier que le son est bien capté.
          </p>

          {error && <p className="settings-error">{error}</p>}

          <label className="settings-label">Périphérique</label>
          <select
            className="settings-select"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={loading}
          >
            <option value="">
              Haut-parleur par défaut {defaultSpeaker ? `(${defaultSpeaker})` : ''}
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
              {testing ? 'Mesure…' : 'Tester le son'}
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
                ? "Erreur de capture sur ce périphérique"
                : level > 0.001
                ? `Son détecté ✓ (niveau ${Math.round(level * 1000) / 10}%)`
                : "Aucun son capté — lisez un son puis retestez"}
            </p>
          )}

          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={saving}
            style={saved ? { backgroundColor: 'rgba(222,255,154,0.5)' } : {}}
          >
            {saved ? 'Enregistré ✓' : saving ? 'Enregistrement…' : 'Enregistrer le choix'}
          </button>
        </div>

        {/* --- Test bracelet --- */}
        <div className="settings-section">
          <h3>Test du Bracelet</h3>
          <div className="settings-actions">
            <button
              className="btn-test-severe"
              onClick={() => onTestVibration('severe')}
            >
              Tester Alerte Sévère
            </button>
            <button
              className="btn-test-vigilance"
              onClick={() => onTestVibration('vigilance')}
            >
              Tester Vigilance
            </button>
          </div>
        </div>

        <button className="btn-outline" onClick={onClose}>
          Fermer
        </button>
      </div>
    </div>
  )
}
