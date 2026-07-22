const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  setIgnoreMouseEvents: (ignore, options) => ipcRenderer.send('set-ignore-mouse-events', ignore, options),
  updateWindow: (action, deltaX, deltaY) => ipcRenderer.send('update-window', action, deltaX, deltaY),
  getBounds: () => ipcRenderer.invoke('get-bounds'),
  setBounds: (bounds) => ipcRenderer.send('set-bounds', bounds),
  openDashboard: () => ipcRenderer.send('open-dashboard'),
  stopSession: () => ipcRenderer.send('stop-session'),
  closeApp: () => ipcRenderer.send('close-app'),
  connectBLE: () => ipcRenderer.invoke('connect-ble'),
  disconnectBLE: () => ipcRenderer.invoke('disconnect-ble'),
  getBLEStatus: () => ipcRenderer.invoke('get-ble-status'),
  saveSessionReport: (payload) => ipcRenderer.invoke('save-session-report', payload),
  audioDevices: () => ipcRenderer.invoke('audio-devices'),
  audioTest: (deviceId, duration) => ipcRenderer.invoke('audio-test', deviceId, duration),
  audioSetDevice: (deviceId) => ipcRenderer.invoke('audio-set-device', deviceId),
})
