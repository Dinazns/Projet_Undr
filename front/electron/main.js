const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const { pathToFileURL } = require('url')

let hudWindow
let dashboardWindow

function createHUD() {
  hudWindow = new BrowserWindow({
    width: 800,
    height: 600,
    minWidth: 400,
    minHeight: 300,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    hasShadow: false,
    resizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  // En dev, charge le serveur Vite. En prod, charge le build statique.
  if (process.env.VITE_DEV_SERVER_URL) {
    hudWindow.loadURL(`${process.env.VITE_DEV_SERVER_URL}#/hud`)
  } else {
    const filePath = path.join(__dirname, '../dist/index.html')
    hudWindow.loadURL(pathToFileURL(filePath).href + '#/hud')
  }
}

function createDashboard() {
  dashboardWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    title: 'Undr - Dashboard de session',
    autoHideMenuBar: true,
    backgroundColor: '#0a0a0a',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  if (process.env.VITE_DEV_SERVER_URL) {
    dashboardWindow.loadURL(`${process.env.VITE_DEV_SERVER_URL}#/dashboard`)
  } else {
    const filePath = path.join(__dirname, '../dist/index.html')
    dashboardWindow.loadURL(pathToFileURL(filePath).href + '#/dashboard')
  }
}

app.whenReady().then(() => {
  createHUD()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createHUD()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// --- IPC Handlers ---

ipcMain.on('set-ignore-mouse-events', (event, ignore, options) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win) {
    win.setIgnoreMouseEvents(ignore, options)
  }
})

ipcMain.on('set-bounds', (event, bounds) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win && bounds) {
    win.setBounds({ x: bounds.x, y: bounds.y, width: bounds.w, height: bounds.h })
  }
})

ipcMain.handle('get-bounds', (event) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win) {
    const b = win.getBounds()
    return { x: b.x, y: b.y, w: b.width, h: b.height }
  }
  return { x: 0, y: 0, w: 0, h: 0 }
})

ipcMain.on('update-window', (event, action, deltaX, deltaY) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (!win) return

  let [x, y] = win.getPosition()
  let [w, h] = win.getSize()

  if (action === 'move') {
    x += deltaX
    y += deltaY
  } else {
    if (action.includes('n')) {
      const oldH = h
      h = Math.max(300, h - deltaY)
      y += oldH - h
    }
    if (action.includes('s')) {
      h = Math.max(300, h + deltaY)
    }
    if (action.includes('w')) {
      const oldW = w
      w = Math.max(400, w - deltaX)
      x += oldW - w
    }
    if (action.includes('e')) {
      w = Math.max(400, w + deltaX)
    }
  }

  win.setBounds({ x, y, width: w, height: h })
})

ipcMain.on('stop-session', () => {
  if (hudWindow) {
    hudWindow.close()
  }
  createDashboard()
})

ipcMain.on('close-app', () => {
  app.quit()
})
