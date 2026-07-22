import { useState, useMemo, useEffect } from 'react'
import { useElectron } from '../hooks/useElectron'
import { store } from '../lib/store'
import DissonanceChart from '../components/DissonanceChart'
import ValenceChart from '../components/ValenceChart'
import RussellChart from '../components/RussellChart'
import '../styles/dashboard.css'

export default function Dashboard() {
  const electron = useElectron()
  const [notes, setNotes] = useState('')
  const [saveStatus, setSaveStatus] = useState('idle') // 'idle' | 'saved' | 'error'
  const [dissonanceData, setDissonanceData] = useState(() => store.getDissonances())
  const [selectedIndex, setSelectedIndex] = useState(null)

  // Synchronisation cross-fenêtre via localStorage events
  useEffect(() => {
    const handleStorage = (e) => {
      if (e.key === 'dissonanceData') {
        setDissonanceData(store.getDissonances())
        setSelectedIndex(null)
      }
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  const { totalAlerts, positiveCount, negativeCount, neutralCount } = useMemo(() => {
    let alerts = 0
    let pos = 0
    let neg = 0
    let neu = 0

    for (const d of dissonanceData) {
      if (d.alert_level === 'SEVERE' || d.alert_level === 'MODERATE') {
        alerts++
      }
      // Valence multimodale : moyenne de la valence (X du plan de Russell) des
      // deux canaux. Repli sur un seul canal si l'autre est absent (anciennes
      // sessions sans voice_coords). Seuil ±0.1 pour isoler le neutre.
      const fv = d.face_coords ? d.face_coords[0] : null
      const vv = d.voice_coords ? d.voice_coords[0] : null
      let valence = null
      if (fv != null && vv != null) valence = (fv + vv) / 2
      else if (fv != null) valence = fv
      else if (vv != null) valence = vv
      if (valence != null) {
        if (valence > 0.1) pos++
        else if (valence < -0.1) neg++
        else neu++
      }
    }

    return { totalAlerts: alerts, positiveCount: pos, negativeCount: neg, neutralCount: neu }
  }, [dissonanceData])

  const handleSave = async () => {
    if (!electron?.saveSessionReport) {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus('idle'), 2500)
      return
    }

    const now = new Date()
    const report = {
      app: 'Undr',
      exported_at: now.toISOString(),
      session_summary: {
        total_entries: dissonanceData.length,
        total_alerts: totalAlerts,
        positive_face_count: positiveCount,
        negative_face_count: negativeCount,
      },
      clinical_notes: notes.trim() || null,
      dissonance_entries: dissonanceData,
    }

    const result = await electron.saveSessionReport(report)
    if (result?.success) {
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 2500)
      return
    }

    if (!result?.canceled) {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus('idle'), 2500)
    }
  }

  const handleClose = () => {
    if (electron) electron.closeApp()
  }

  const saveButtonText =
    saveStatus === 'saved'
      ? 'Enregistré'
      : saveStatus === 'error'
      ? "Erreur d'enregistrement"
      : 'Enregistrer le compte-rendu PDF'

  const saveButtonStyle =
    saveStatus === 'error'
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
              <DissonanceChart
                data={dissonanceData}
                onSelectEntry={(idx) => setSelectedIndex(idx)}
              />
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
              <h2>Valence Émotionnelle (Voix + Visage)</h2>
            </div>
            <div className="chart-container doughnut-container">
              <ValenceChart positive={positiveCount} negative={negativeCount} neutral={neutralCount} />
            </div>
          </div>

          <div className="glass-panel chart-section">
            <div className="section-header">
              <h2>Mapping de Russell (Visage ↔ Voix)</h2>
            </div>
            <div className="chart-container russell-container">
              {selectedIndex != null && dissonanceData[selectedIndex] ? (
                <RussellChart entry={dissonanceData[selectedIndex]} />
              ) : (
                <p style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'center' }}>
                  Cliquez sur un pic de la timeline pour afficher les coordonnées
                  exactes (valence / arousal) du visage et de la voix à cet instant T.
                </p>
              )}
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
