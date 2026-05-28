const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    setIgnoreMouseEvents: (ignore, options) => ipcRenderer.send('set-ignore-mouse-events', ignore, options),
    updateWindow: (action, deltaX, deltaY) => ipcRenderer.send('update-window', action, deltaX, deltaY),
    getBounds: () => ipcRenderer.invoke('get-bounds'),
    setBounds: (bounds) => ipcRenderer.send('set-bounds', bounds),
    stopSession: () => ipcRenderer.send('stop-session'),
    closeApp: () => ipcRenderer.send('close-app')
});
