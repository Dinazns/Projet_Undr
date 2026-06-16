import { useState } from 'react'
import { store } from '../lib/store'

export default function SettingsModal({ onClose, onTestVibration }) {
  const [intensity, setIntensity] = useState(store.getVibrationIntensity())

  const handleIntensityChange = (e) => {
    const val = parseInt(e.target.value, 10)
    setIntensity(val)
    store.setVibrationIntensity(val)
  }

  return (
    <div className="settings-overlay">
      <div className="settings-panel glass-panel">
        <h2>Paramètres</h2>

        <div className="settings-section">
          <h3>Test du Bracelet</h3>
          <div className="settings-group">
            <label htmlFor="vibration-intensity">
              Puissance de vibration par défaut ({intensity})
            </label>
            <input
              type="range"
              id="vibration-intensity"
              min="0"
              max="100"
              value={intensity}
              onChange={handleIntensityChange}
            />
          </div>
          <div className="settings-actions">
            <button
              className="btn-test-severe"
              onClick={() => onTestVibration('severe', intensity)}
            >
              Tester Alerte Sévère
            </button>
            <button
              className="btn-test-vigilance"
              onClick={() => onTestVibration('vigilance', intensity)}
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
