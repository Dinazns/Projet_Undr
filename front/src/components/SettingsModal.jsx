export default function SettingsModal({ onClose, onTestVibration }) {
  return (
    <div className="settings-overlay">
      <div className="settings-panel glass-panel">
        <h2>Paramètres</h2>

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
