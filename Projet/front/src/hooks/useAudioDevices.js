import { useState, useEffect, useCallback } from 'react'
import { useElectron } from './useElectron'

/**
 * Hook de gestion du périphérique de capture audio (loopback).
 * Expose la liste des périphériques, le choix courant, et un test de niveau
 * sonore pour vérifier que le son est bien capté avant de lancer une session.
 */
export function useAudioDevices() {
  const electron = useElectron()
  const [devices, setDevices] = useState([])
  const [current, setCurrent] = useState(null)
  const [defaultSpeaker, setDefaultSpeaker] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!electron?.audioDevices) {
      setError('API audio non disponible (backend éteint ?)')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await electron.audioDevices()
      setDevices(data.devices || [])
      setCurrent(data.current || null)
      setDefaultSpeaker(data.default_speaker || null)
      if (data.error) setError(data.error)
    } catch (e) {
      setError(e.message || 'Erreur de liste audio')
    } finally {
      setLoading(false)
    }
  }, [electron])

  useEffect(() => {
    refresh()
  }, [refresh])

  const testDevice = useCallback(
    async (deviceId, duration = 1.5) => {
      if (!electron?.audioTest) {
        throw new Error('API test audio non disponible')
      }
      return await electron.audioTest(deviceId || null, duration)
    },
    [electron],
  )

  const selectDevice = useCallback(
    async (deviceId) => {
      if (!electron?.audioSetDevice) {
        throw new Error('API choix audio non disponible')
      }
      const res = await electron.audioSetDevice(deviceId || null)
      if (res?.status === 'ok') {
        setCurrent(deviceId || null)
      } else if (res?.status === 'error') {
        setError(res.error)
      }
      return res
    },
    [electron],
  )

  return {
    devices,
    current,
    defaultSpeaker,
    loading,
    error,
    refresh,
    testDevice,
    selectDevice,
  }
}