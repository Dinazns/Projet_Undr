import { useState, useEffect, useCallback } from 'react'
import { useElectron } from './useElectron'
import { t } from '../lib/i18n'

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
      setError(t('audioApiUnavailable'))
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
      setError(e.message || t('audioListError'))
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
        throw new Error(t('audioTestUnavailable'))
      }
      return await electron.audioTest(deviceId || null, duration)
    },
    [electron],
  )

  const selectDevice = useCallback(
    async (deviceId) => {
      if (!electron?.audioSetDevice) {
        throw new Error(t('audioSelectUnavailable'))
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