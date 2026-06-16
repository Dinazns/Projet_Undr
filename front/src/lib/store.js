import { DISSONANCE_DATA_KEY, VIBRATION_INTENSITY_KEY, HUD_BOUNDS_KEY } from './constants'

/**
 * Store simple basé sur localStorage pour persister les données de session.
 * Permet de conserver les alertes de dissonance entre le HUD et le Dashboard.
 */
export const store = {
  // Dissonances 
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

  // Intensité vibration
  getVibrationIntensity() {
    const raw = localStorage.getItem(VIBRATION_INTENSITY_KEY)
    return raw ? parseInt(raw, 10) : 50
  },

  setVibrationIntensity(value) {
    localStorage.setItem(VIBRATION_INTENSITY_KEY, String(value))
  },

  //  Bounds du HUD
  getHudBounds() {
    try {
      const raw = localStorage.getItem(HUD_BOUNDS_KEY)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  },

  setHudBounds(bounds) {
    localStorage.setItem(HUD_BOUNDS_KEY, JSON.stringify(bounds))
  },
}
