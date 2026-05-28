document.addEventListener('DOMContentLoaded', () => {
    // 1. Restore HUD bounds on load
    const savedBoundsStr = localStorage.getItem('hudBounds');
    if (savedBoundsStr) {
        try {
            const savedBounds = JSON.parse(savedBoundsStr);
            if (savedBounds && window.electronAPI && window.electronAPI.setBounds) {
                window.electronAPI.setBounds(savedBounds);
            }
        } catch (e) {
            console.error("Erreur de restauration des bounds", e);
        }
    }

    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    const waitingScreen = document.getElementById('waiting-screen');
    const activeScreen = document.getElementById('active-screen');
    const appContainer = document.getElementById('app-container');

    const btnSettings = document.getElementById('btn-settings');
    const btnCloseSettings = document.getElementById('btn-close-settings');
    const settingsModal = document.getElementById('settings-modal');
    
    const intensitySlider = document.getElementById('vibration-intensity');
    const intensityVal = document.getElementById('intensity-val');
    const btnTestSevere = document.getElementById('btn-test-severe');
    const btnTestVigilance = document.getElementById('btn-test-vigilance');

    let ws;

    // Load saved intensity
    const savedIntensity = localStorage.getItem('vibrationIntensity');
    if (savedIntensity && intensitySlider) {
        intensitySlider.value = savedIntensity;
        intensityVal.innerText = savedIntensity;
    }

    if (intensitySlider) {
        intensitySlider.addEventListener('input', (e) => {
            intensityVal.innerText = e.target.value;
            localStorage.setItem('vibrationIntensity', e.target.value);
        });
    }

    if (btnSettings) {
        btnSettings.addEventListener('click', () => {
            settingsModal.classList.remove('hidden');
            if (appContainer.classList.contains('state-active')) {
                window.electronAPI.setIgnoreMouseEvents(false);
            }
        });
    }

    if (btnCloseSettings) {
        btnCloseSettings.addEventListener('click', () => {
            settingsModal.classList.add('hidden');
            if (appContainer.classList.contains('state-active')) {
                window.electronAPI.setIgnoreMouseEvents(true, { forward: true });
            }
        });
    }

    function sendVibrationTest(type, intensity) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'test_vibration',
                test_type: type,
                intensity: parseInt(intensity)
            }));
        } else {
            console.log("WebSocket non connecté. Test impossible.");
        }
    }

    if (btnTestSevere) {
        btnTestSevere.addEventListener('click', () => {
            sendVibrationTest('severe', intensitySlider.value);
        });
    }

    if (btnTestVigilance) {
        btnTestVigilance.addEventListener('click', () => {
            sendVibrationTest('vigilance', intensitySlider.value);
        });
    }

    if (btnStart) {
        btnStart.addEventListener('click', () => {
            waitingScreen.classList.add('hidden');
            activeScreen.classList.remove('hidden');
            appContainer.classList.remove('state-waiting');
            appContainer.classList.add('state-active');
            window.electronAPI.setIgnoreMouseEvents(true, { forward: true });

            // Clear previous session data
            localStorage.removeItem('dissonanceData');

            // Connexion au Backend FastAPI
            ws = new WebSocket('ws://127.0.0.1:8000/ws');

            ws.onopen = () => {
                console.log("Connecté au moteur Python !");
                // Mettre à jour l'API LED
                document.querySelector('.api-led').classList.remove('red');
                document.querySelector('.api-led').classList.add('green');
                
                // Envoyer la Bounding Box initiale
                envoyerCoordonnees();
                // Actualiser à intervalles réguliers au cas où
                setInterval(envoyerCoordonnees, 500);
            };

            ws.onerror = () => {
                document.querySelector('.api-led').classList.remove('green');
                document.querySelector('.api-led').classList.add('red');
            };

            ws.onclose = () => {
                document.querySelector('.api-led').classList.remove('green');
                document.querySelector('.api-led').classList.add('red');
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'dissonance') {
                    // Mettre à jour la LED du capteur s'il y a des données
                    document.querySelector('.bracelet-led').classList.add('green');

                    // Sauvegarder les données pour le dashboard (localStorage partagé dans Electron)
                    const dissonanceData = JSON.parse(localStorage.getItem('dissonanceData') || '[]');
                    dissonanceData.push({
                        time: data.timestamp,
                        value: Math.round(data.value),
                        alert_level: data.alert_level,
                        face: data.face,
                        voice: data.voice,
                        quadrant_face: data.quadrant_face
                    });
                    localStorage.setItem('dissonanceData', JSON.stringify(dissonanceData));
                }
            };
        });
    }

    function envoyerCoordonnees() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            window.electronAPI.getBounds().then(bounds => {
                ws.send(JSON.stringify(bounds));
            });
        }
    }

    if (btnStop) {
        btnStop.addEventListener('click', () => {
            window.electronAPI.stopSession();
        });
    }

    // Universal Interaction Logic (Drag & Resize via IPC)
    let currentAction = null;
    let startScreenX, startScreenY;

    const interactables = document.querySelectorAll('.interact-edge, .move-edge, #mini-widget, .main-panel');
    
    interactables.forEach(el => {
        el.addEventListener('pointerdown', (e) => {
            // Ignore si clic sur un bouton ou slider, ou à l'intérieur de la modale de paramètres
            if (e.target.tagName === 'BUTTON' || e.target.closest('button') || e.target.tagName === 'INPUT' || e.target.closest('#settings-modal')) return;
            
            const action = el.dataset.action || (el.id === 'mini-widget' || el.classList.contains('main-panel') ? 'move' : null);
            if (!action) return;

            currentAction = action;
            startScreenX = e.screenX;
            startScreenY = e.screenY;

            el.setPointerCapture(e.pointerId);
            
            if (appContainer.classList.contains('state-active')) {
                window.electronAPI.setIgnoreMouseEvents(false);
            }
        });

        el.addEventListener('pointermove', (e) => {
            if (!currentAction) return;
            
            const deltaX = e.screenX - startScreenX;
            const deltaY = e.screenY - startScreenY;
            
            startScreenX = e.screenX;
            startScreenY = e.screenY;

            window.electronAPI.updateWindow(currentAction, deltaX, deltaY);
        });

        el.addEventListener('pointerup', (e) => {
            if (currentAction) {
                currentAction = null;
                el.releasePointerCapture(e.pointerId);
                
                // Enregistrement de la position et de la taille
                window.electronAPI.getBounds().then(bounds => {
                    localStorage.setItem('hudBounds', JSON.stringify(bounds));
                    envoyerCoordonnees();
                });
                
                if (appContainer.classList.contains('state-active') && !el.matches(':hover')) {
                    if (!settingsModal || settingsModal.classList.contains('hidden')) {
                        window.electronAPI.setIgnoreMouseEvents(true, { forward: true });
                    }
                }
            }
        });

        el.addEventListener('pointerenter', () => {
            if (appContainer.classList.contains('state-active') && !currentAction) {
                window.electronAPI.setIgnoreMouseEvents(false);
            }
        });

        el.addEventListener('pointerleave', () => {
            if (appContainer.classList.contains('state-active') && !currentAction) {
                if (!settingsModal || settingsModal.classList.contains('hidden')) {
                    window.electronAPI.setIgnoreMouseEvents(true, { forward: true });
                }
            }
        });
    });
});
