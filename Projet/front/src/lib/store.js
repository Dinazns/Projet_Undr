import { DISSONANCE_DATA_KEY, CONSENT_KEY } from './constants'

/**
 * Store simple basé sur localStorage pour persister les données de session.
 * Permet de conserver les alertes de dissonance entre le HUD et le Dashboard.
 */
export const store = {
  getDissonances() {
    try {
      const raw = localStorage.getItem(DISSONANCE_DATA_KEY)
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  },

  addDissonance(entry) {
    const data = this.getDissonances()
    data.push(entry)
    localStorage.setItem(DISSONANCE_DATA_KEY, JSON.stringify(data))
  },

  clearDissonances() {
    localStorage.removeItem(DISSONANCE_DATA_KEY)
  },

  /**
   * Horodate l'attestation de consentement. Le patient n'a pas accès à
   * l'interface : c'est le praticien qui l'informe et qui atteste de son
   * accord. Un consentement recueilli par un tiers ne vaut que s'il est tracé,
   * d'où cet horodatage, repris sur le compte-rendu de séance.
   */
  recordConsent() {
    const timestamp = new Date().toISOString()
    localStorage.setItem(CONSENT_KEY, timestamp)
    return timestamp
  },

  getConsent() {
    return localStorage.getItem(CONSENT_KEY)
  },

  clearConsent() {
    localStorage.removeItem(CONSENT_KEY)
  },
}
