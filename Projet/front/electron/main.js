const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const path = require('path')
const { pathToFileURL } = require('url')
const fs = require('fs')

let hudWindow
let dashboardWindow

const BOUNDS_FILE = path.join(app.getPath('userData'), 'hud-bounds.json')

function loadHudBounds() {
  try {
    const data = fs.readFileSync(BOUNDS_FILE, 'utf-8')
    return JSON.parse(data)
  } catch {
    return null
  }
}

function saveHudBounds(bounds) {
  try {
    const dir = path.dirname(BOUNDS_FILE)
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true })
    }
    fs.writeFileSync(BOUNDS_FILE, JSON.stringify(bounds), 'utf-8')
  } catch (e) {
    console.error('Erreur sauvegarde bounds:', e)
  }
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function buildSessionReportHtml(payload) {
  const exportedAt = payload?.exported_at
    ? new Date(payload.exported_at).toLocaleString('fr-FR')
    : new Date().toLocaleString('fr-FR')

  const summary = payload?.session_summary || {}
  const notes = payload?.clinical_notes
    ? `<div class="notes">${escapeHtml(payload.clinical_notes)}</div>`
    : '<div class="notes notes-empty">Aucune note clinique saisie.</div>'

  const rows = (payload?.dissonance_entries || [])
    .map((entry, index) => `
      <tr>
        <td>${index + 1}</td>
        <td>${escapeHtml(entry.time)}</td>
        <td>${escapeHtml(entry.alert_level)}</td>
        <td>${escapeHtml(entry.value)}</td>
        <td>${escapeHtml(entry.face)}</td>
        <td>${escapeHtml(entry.voice)}</td>
      </tr>
    `)
    .join('')

  const tableBody = rows || `
    <tr>
      <td colspan="6" class="empty-row">Aucune dissonance enregistrée pendant cette séance.</td>
    </tr>
  `

  return `
    <!DOCTYPE html>
    <html lang="fr">
      <head>
        <meta charset="UTF-8" />
        <title>Compte-rendu Undr</title>
        <style>
          * { box-sizing: border-box; }
          body {
            font-family: Arial, Helvetica, sans-serif;
            color: #102033;
            margin: 0;
            padding: 32px;
            background: #f4f7fb;
          }
          .page {
            background: #ffffff;
            border-radius: 18px;
            padding: 32px;
            border: 1px solid #d9e2ef;
          }
          .header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 24px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e8eef7;
            margin-bottom: 24px;
          }
          .brand {
            font-size: 28px;
            font-weight: 700;
            color: #1d4ed8;
            margin-bottom: 8px;
          }
          .subtitle {
            font-size: 18px;
            font-weight: 600;
            margin: 0 0 8px 0;
          }
          .meta {
            font-size: 13px;
            color: #5b6b7f;
            text-align: right;
          }
          .section-title {
            font-size: 18px;
            font-weight: 700;
            margin: 0 0 14px 0;
            color: #16324f;
          }
          .cards {
            display: flex;
            gap: 16px;
            margin-bottom: 28px;
          }
          .card {
            flex: 1;
            background: linear-gradient(135deg, #eff6ff, #f8fbff);
            border: 1px solid #d7e5ff;
            border-radius: 14px;
            padding: 16px;
          }
          .card-label {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #5b6b7f;
            margin-bottom: 8px;
          }
          .card-value {
            font-size: 28px;
            font-weight: 700;
            color: #16324f;
          }
          .notes {
            min-height: 72px;
            background: #f8fafc;
            border: 1px solid #d9e2ef;
            border-radius: 12px;
            padding: 14px 16px;
            line-height: 1.5;
            white-space: pre-wrap;
            margin-bottom: 28px;
          }
          .notes-empty {
            color: #718096;
            font-style: italic;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
          }
          thead th {
            background: #16324f;
            color: white;
            padding: 10px;
            text-align: left;
          }
          tbody td {
            padding: 10px;
            border-bottom: 1px solid #e8eef7;
            vertical-align: top;
          }
          tbody tr:nth-child(even) {
            background: #f8fbff;
          }
          .empty-row {
            text-align: center;
            color: #718096;
            font-style: italic;
            padding: 18px;
          }
          .footer {
            margin-top: 24px;
            font-size: 11px;
            color: #718096;
            text-align: right;
          }
        </style>
      </head>
      <body>
        <div class="page">
          <div class="header">
            <div>
              <div class="brand">Undr</div>
              <p class="subtitle">Compte-rendu de séance</p>
            </div>
            <div class="meta">
              <div><strong>Date d'export :</strong> ${escapeHtml(exportedAt)}</div>
              <div><strong>Application :</strong> ${escapeHtml(payload?.app || 'Undr')}</div>
            </div>
          </div>

          <h2 class="section-title">Résumé de séance</h2>
          <div class="cards">
            <div class="card">
              <div class="card-label">Entrées</div>
              <div class="card-value">${escapeHtml(summary.total_entries ?? 0)}</div>
            </div>
            <div class="card">
              <div class="card-label">Alertes</div>
              <div class="card-value">${escapeHtml(summary.total_alerts ?? 0)}</div>
            </div>
            <div class="card">
              <div class="card-label">Valence positive</div>
              <div class="card-value">${escapeHtml(summary.positive_face_count ?? 0)}</div>
            </div>
            <div class="card">
              <div class="card-label">Valence négative</div>
              <div class="card-value">${escapeHtml(summary.negative_face_count ?? 0)}</div>
            </div>
          </div>

          <h2 class="section-title">Notes cliniques</h2>
          ${notes}

          <h2 class="section-title">Détail des dissonances</h2>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Heure</th>
                <th>Niveau</th>
                <th>Score</th>
                <th>Visage</th>
                <th>Voix</th>
              </tr>
            </thead>
            <tbody>
              ${tableBody}
            </tbody>
          </table>

          <div class="footer">
            Rapport généré automatiquement par Undr
          </div>
        </div>
      </body>
    </html>
  `
}

function createHUD() {
  const saved = loadHudBounds()

  hudWindow = new BrowserWindow({
    width: 800,
    height: 600,
    minWidth: 400,
    minHeight: 300,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    hasShadow: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })


  hudWindow.setMovable(false)

  // Applique les bounds sauvegardees quand la fenetre est prete
  hudWindow.once('ready-to-show', () => {
    if (saved && saved.x !== undefined && saved.y !== undefined) {
      hudWindow.setBounds(saved)
    }
  })

  // Sauvegarde la position et taille a la fermeture
  hudWindow.on('close', () => {
    if (hudWindow && !hudWindow.isDestroyed()) {
      saveHudBounds(hudWindow.getBounds())
    }
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

app.on('before-quit', () => {
  if (hudWindow && !hudWindow.isDestroyed()) {
    saveHudBounds(hudWindow.getBounds())
  }
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

ipcMain.on('open-dashboard', () => {
  if (!dashboardWindow || dashboardWindow.isDestroyed()) {
    createDashboard()
  } else {
    if (dashboardWindow.isMinimized()) dashboardWindow.restore()
    dashboardWindow.focus()
  }
})

ipcMain.on('stop-session', () => {
  if (hudWindow) {
    hudWindow.close()
    hudWindow = null
  }
  if (!dashboardWindow || dashboardWindow.isDestroyed()) {
    createDashboard()
  }
})

ipcMain.on('close-app', () => {
  app.quit()
})

// --- BLE IPC Handlers ---

ipcMain.handle('connect-ble', async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/ble/connect', {
      method: 'POST',
    })
    const data = await response.json()
    return data
  } catch (e) {
    console.error('Erreur connexion BLE:', e)
    return {
      status: 'error',
      error: e.message,
      ble_connected: false,
    }
  }
})

ipcMain.handle('disconnect-ble', async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/ble/disconnect', {
      method: 'POST',
    })
    const data = await response.json()
    return data
  } catch (e) {
    console.error('Erreur déconnexion BLE:', e)
    return {
      status: 'error',
      error: e.message,
      ble_connected: false,
    }
  }
})

ipcMain.handle('get-ble-status', async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/ble/status')
    const data = await response.json()
    return data
  } catch (e) {
    console.error('Erreur statut BLE:', e)
    return {
      ble_connected: false,
    }
  }
})

// --- Audio IPC Handlers (choix du périphérique loopback) ---

ipcMain.handle('audio-devices', async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/audio/devices')
    return await response.json()
  } catch (e) {
    console.error('Erreur liste peripheriques audio:', e)
    return { current: null, default_speaker: null, devices: [], error: e.message }
  }
})

ipcMain.handle('audio-test', async (_event, deviceId, duration) => {
  try {
    const params = new URLSearchParams()
    if (deviceId) params.set('device_id', deviceId)
    if (duration) params.set('duration', String(duration))
    const response = await fetch(`http://127.0.0.1:8000/audio/test?${params.toString()}`)
    return await response.json()
  } catch (e) {
    console.error('Erreur test audio:', e)
    return { device_id: deviceId, energy: -1, has_signal: false, error: e.message }
  }
})

ipcMain.handle('audio-set-device', async (_event, deviceId) => {
  try {
    const response = await fetch('http://127.0.0.1:8000/audio/device', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: deviceId || null }),
    })
    return await response.json()
  } catch (e) {
    console.error('Erreur choix peripherique audio:', e)
    return { status: 'error', error: e.message }
  }
})

ipcMain.handle('save-session-report', async (_event, payload) => {
  try {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
    const defaultPath = path.join(
      app.getPath('documents'),
      `undr-session-${timestamp}.pdf`
    )

    const result = await dialog.showSaveDialog({
      title: 'Enregistrer le compte-rendu de séance',
      defaultPath,
      filters: [
        { name: 'Fichier PDF', extensions: ['pdf'] },
      ],
    })

    if (result.canceled || !result.filePath) {
      return {
        success: false,
        canceled: true,
      }
    }

    const pdfWindow = new BrowserWindow({
      show: false,
      webPreferences: {
        sandbox: true,
      },
    })

    const html = buildSessionReportHtml(payload)
    await pdfWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`)
    const pdfData = await pdfWindow.webContents.printToPDF({
      printBackground: true,
      pageSize: 'A4',
      margins: {
        top: 0,
        bottom: 0,
        left: 0,
        right: 0,
      },
    })
    fs.writeFileSync(result.filePath, pdfData)
    pdfWindow.destroy()

    return {
      success: true,
      filePath: result.filePath,
    }
  } catch (e) {
    console.error("Erreur lors de l'enregistrement du compte-rendu:", e)
    return {
      success: false,
      canceled: false,
      error: e.message,
    }
  }
})
