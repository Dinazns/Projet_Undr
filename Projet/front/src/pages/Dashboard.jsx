import { useState, useMemo, useEffect } from 'react'
import { useElectron } from '../hooks/useElectron'
import { store } from '../lib/store'
import { useI18n } from '../lib/i18n'
import DissonanceChart from '../components/DissonanceChart'
import ValenceChart from '../components/ValenceChart'
import RussellChart from '../components/RussellChart'
import '../styles/dashboard.css'

export default function Dashboard() {
  const { t } = useI18n()
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
      // Horodatage de l'attestation de consentement saisie par le praticien.
      consent_recorded_at: store.getConsent(),
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
    // Purge des données de séance avant fermeture. Sans cela, les événements
    // horodatés restent en clair dans le localStorage d'Electron (%APPDATA%)
    // et sont encore présents à l'ouverture de la séance suivante, donc du
    // patient suivant. Ce sont des données inférées sur un état de santé.
    store.clearDissonances()
    store.clearConsent()
    if (electron) electron.closeApp()
  }

  const saveButtonText =
    saveStatus === 'saved'
      ? t('savedShort')
      : saveStatus === 'error'
      ? t('saveError')
      : t('savePdf')

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
          <h1>{t('dashboardTitle')}</h1>
        </div>
        <button className="btn-secondary" onClick={handleClose}>
          {t('closeApp')}
        </button>
      </header>

      <main className="dashboard-grid">
        {/* Timeline des dissonances */}
        <section className="glass-panel chart-section">
          <div className="section-header">
            <h2>{t('timelineTitle')}</h2>
            <span className="badge">{t('alertCount', { n: totalAlerts })}</span>
          </div>
          <div className="chart-container">
            {dissonanceData.length > 0 ? (
              <DissonanceChart
                data={dissonanceData}
                onSelectEntry={(idx) => setSelectedIndex(idx)}
              />
            ) : (
              <p style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'center', paddingTop: 100 }}>
                {t('noData')}
              </p>
            )}
          </div>
        </section>

        {/* Graphiques secondaires */}
        <section className="secondary-charts-grid">
          <div className="glass-panel chart-section">
            <div className="section-header">
              <h2>{t('valenceTitle')}</h2>
            </div>
            <div className="chart-container doughnut-container">
              <ValenceChart positive={positiveCount} negative={negativeCount} neutral={neutralCount} />
            </div>
          </div>

          <div className="glass-panel chart-section">
            <div className="section-header">
              <h2>{t('russellTitle')}</h2>
            </div>
            <div className="chart-container russell-container">
              {selectedIndex != null && dissonanceData[selectedIndex] ? (
                <RussellChart entry={dissonanceData[selectedIndex]} />
              ) : (
                <p style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'center' }}>
                  {t('russellHint')}
                </p>
              )}
            </div>
          </div>
        </section>

        {/* Notes cliniques */}
        <section className="glass-panel notes-section">
          <h2>{t('notesTitle')}</h2>
          <textarea
            placeholder={t('notesPlaceholder')}
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
