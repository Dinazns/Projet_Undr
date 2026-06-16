import { useState, useMemo, useEffect, useCallback } from 'react'
import { useElectron } from '../hooks/useElectron'
import { useWebSocket } from '../hooks/useWebSocket'
import { store } from '../lib/store'
import DissonanceChart from '../components/DissonanceChart'
import ValenceChart from '../components/ValenceChart'
import '../styles/dashboard.css'

export default function Dashboard() {
  const electron = useElectron()
  const [notes, setNotes] = useState('')
  const [saveStatus, setSaveStatus] = useState('idle') // 'idle' | 'saved' | 'empty'
  const [dissonanceData, setDissonanceData] = useState(() => store.getDissonances())

  const handleWsMessage = useCallback((data) => {
    if (data.type === 'dissonance') {
      const entry = {
        time: data.timestamp,
        value: Math.round(data.value),
        alert_level: data.alert_level,
        face: data.face,
        voice: data.voice,
        quadrant_face: data.quadrant_face,
      }
      store.addDissonance(entry)
      setDissonanceData((prev) => [...prev, entry])
    }
  }, [])

  useWebSocket(handleWsMessage)

  // Synchronisation cross-fenêtre via localStorage events
  useEffect(() => {
    const handleStorage = (e) => {
      if (e.key === 'dissonanceData') {
        setDissonanceData(store.getDissonances())
      }
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  const { totalAlerts, positiveCount, negativeCount } = useMemo(() => {
    let alerts = 0
    let pos = 0
    let neg = 0

    for (const d of dissonanceData) {
      if (d.alert_level === 'SEVERE' || d.alert_level === 'MODERATE') {
        alerts++
      }
      if (d.quadrant_face) {
        if (d.quadrant_face.includes('Positif')) pos++
        else if (d.quadrant_face.includes('Négatif')) neg++
      }
    }

    return { totalAlerts: alerts, positiveCount: pos, negativeCount: neg }
  }, [dissonanceData])

  const handleSave = () => {
    if (notes.trim() === '') {
      setSaveStatus('empty')
      setTimeout(() => setSaveStatus('idle'), 2000)
      return
    }

    // Simulation d'enregistrement
    setSaveStatus('saved')
    setTimeout(() => setSaveStatus('idle'), 2000)
  }

  const handleClose = () => {
    if (electron) electron.closeApp()
  }

  const saveButtonText =
    saveStatus === 'saved'
      ? 'Enregistré'
      : saveStatus === 'empty'
      ? "Ajoutez des notes d'abord"
      : 'Enregistrer le compte-rendu'

  const saveButtonStyle =
    saveStatus === 'empty'
      ? { backgroundColor: '#ff5c5c' }
      : saveStatus === 'saved'
      ? { backgroundColor: 'rgba(222, 255, 154, 0.5)' }
      : {}

  return (
    <div className="dashboard-container">
      <header className="glass-panel header-panel">
        <div className="title-group">
          <div className="led green" />
          <h1>Bilan de Téléconsultation</h1>
        </div>
        <button className="btn-secondary" onClick={handleClose}>
          Fermer l'application
        </button>
      </header>

      <main className="dashboard-grid">
        {/* Timeline des dissonances */}
        <section className="glass-panel chart-section">
          <div className="section-header">
            <h2>Timeline des Dissonances Émotionnelles</h2>
            <span className="badge">{totalAlerts} alerte(s)</span>
          </div>
          <div className="chart-container">
            {dissonanceData.length > 0 ? (
              <DissonanceChart data={dissonanceData} />
            ) : (
              <p style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'center', paddingTop: 100 }}>
                Aucune donnée enregistrée pendant cette séance.
              </p>
            )}
          </div>
        </section>

        {/* Graphiques secondaires */}
        <section className="secondary-charts-grid">
          <div className="glass-panel chart-section">
            <div className="section-header">
              <h2>Valence Émotionnelle (Positif/Négatif)</h2>
            </div>
            <div className="chart-container doughnut-container">
              <ValenceChart positive={positiveCount} negative={negativeCount} />
            </div>
          </div>

          <div className="glass-panel chart-section">
            <div className="section-header">
              <h2>Indicateur Secondaire</h2>
            </div>
            <div className="chart-container doughnut-container">
              <p style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'center' }}>
                En développement
              </p>
            </div>
          </div>
        </section>

        {/* Notes cliniques */}
        <section className="glass-panel notes-section">
          <h2>Notes Cliniques</h2>
          <textarea
            placeholder="Saisissez vos observations post-séance ici..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <div className="actions">
            <button
              className="btn-primary"
              style={saveButtonStyle}
              onClick={handleSave}
            >
              {saveButtonText}
            </button>
          </div>
        </section>
      </main>
    </div>
  )
}
