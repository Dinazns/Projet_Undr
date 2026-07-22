/**
 * Hook pour accéder aux APIs Electron exposées par le preload.
 * Retourne null si on n'est pas dans Electron.
 */
export function useElectron() {
  if (typeof window !== 'undefined' && window.electronAPI) {
    return window.electronAPI
  }
  return null
}
