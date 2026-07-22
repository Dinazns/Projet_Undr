import { DISSONANCE_DATA_KEY } from './constants'

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
}
