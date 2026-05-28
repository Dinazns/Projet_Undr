// Simulate some websocket data for the chart initially since Step 3 is FastAPI
// We will structure it so it's ready to receive data via ws://

document.addEventListener('DOMContentLoaded', () => {
    let currentLanguage = "fr";

    function translateEmotion(emotionString) {
        if (!emotionString || typeof emotionString !== 'string') return emotionString;
        
        // Extraction du nom de l'émotion et du pourcentage (ex: "Joy (85%)" -> "Joy", " (85%)")
        const match = emotionString.match(/^(.+?)( \(\d+%\))?$/);
        if (match) {
            const englishName = match[1];
            const percentage = match[2] || '';
            
            if (window.translations && window.translations[currentLanguage]) {
                const translated = window.translations[currentLanguage][englishName];
                if (translated) {
                    return translated + percentage;
                }
            }
        }
        return emotionString;
    }

    const ctx = document.getElementById('dissonanceChart').getContext('2d');
    const alertCounter = document.getElementById('alert-counter');
    let totalAlerts = 0;

    // Chart.js Configuration
    // We want a minimalist dark theme chart.
    Chart.defaults.color = 'rgba(255, 255, 255, 0.6)';
    Chart.defaults.font.family = "'Inter', sans-serif";

    const data = {
        labels: [], // Time labels
        datasets: [
            {
                label: 'Niveau de Dissonance',
                data: [],
                borderColor: '#deff9a',
                backgroundColor: 'rgba(222, 255, 154, 0.1)',
                borderWidth: 2,
                tension: 0.4, // Smooth curve
                fill: true,
                pointBackgroundColor: [], // Dynamic colors for alerts
                pointBorderColor: 'transparent',
                pointRadius: [], // Dynamic radius for alerts
                pointHoverRadius: 6
            }
        ]
    };

    const config = {
        type: 'line',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false // Minimalist
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 15, 15, 0.9)',
                    titleColor: '#deff9a',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: false,
                    callbacks: {
                        title: function(context) {
                            return context[0].label;
                        },
                        label: function(context) {
                            const raw = context.raw;
                            return [
                                `Dissonance : ${context.parsed.y}%`,
                                `👁️ Visage : ${translateEmotion(raw.face) || 'N/A'}`,
                                `🗣️ Voix : ${translateEmotion(raw.voice) || 'N/A'}`
                            ];
                        }
                    }
                },
                zoom: {
                    zoom: {
                        wheel: { enabled: true },
                        pinch: { enabled: true },
                        mode: 'x'
                    },
                    pan: {
                        enabled: true,
                        mode: 'x'
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                        drawBorder: false
                    },
                    ticks: {
                        maxTicksLimit: 10
                    }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                        drawBorder: false
                    },
                    ticks: {
                        stepSize: 25,
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            }
        }
    };

    const dissonanceChart = new Chart(ctx, config);

    // Valence Chart Configuration
    let positiveCount = 0;
    let negativeCount = 0;
    const valenceCtx = document.getElementById('valenceChart').getContext('2d');
    const valenceChart = new Chart(valenceCtx, {
        type: 'doughnut',
        data: {
            labels: ['Positif', 'Négatif'],
            datasets: [{
                data: [0, 0],
                backgroundColor: [
                    '#deff9a', 
                    'rgba(255, 255, 255, 0.1)'
                ],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: 'rgba(255, 255, 255, 0.6)' }
                }
            }
        }
    });

    function addDataPoint(time, value, alert_level, face, voice, quadrant_face) {
        const dataset = dissonanceChart.data.datasets[0];
        
        dissonanceChart.data.labels.push(time);
        dataset.data.push({x: time, y: value, face: face, voice: voice});

        // Styling points based on alert status
        if (alert_level === "SEVERE") {
            dataset.pointBackgroundColor.push('#ff5c5c'); // Red
            dataset.pointRadius.push(6);
            totalAlerts++;
        } else if (alert_level === "MODERATE") {
            dataset.pointBackgroundColor.push('#ffa500'); // Orange
            dataset.pointRadius.push(5);
            totalAlerts++;
        } else if (alert_level === "VIGILANCE") {
            dataset.pointBackgroundColor.push('#ffff00'); // Yellow
            dataset.pointRadius.push(4);
        } else {
            dataset.pointBackgroundColor.push('#deff9a'); // Normal point
            dataset.pointRadius.push(0); // Hidden unless hover
        }

        // Update counter only for SEVERE and MODERATE
        if (alert_level === "SEVERE" || alert_level === "MODERATE") {
            alertCounter.innerText = `${totalAlerts} alerte(s)`;
            
            // Pulse effect on badge
            alertCounter.style.transform = 'scale(1.1)';
            setTimeout(() => {
                alertCounter.style.transform = 'scale(1)';
            }, 200);
        }

        if (quadrant_face) {
            if (quadrant_face.includes('Positif')) {
                positiveCount++;
            } else if (quadrant_face.includes('Négatif')) {
                negativeCount++;
            }
            valenceChart.data.datasets[0].data = [positiveCount, negativeCount];
            valenceChart.update();
        }

        dissonanceChart.update();
    }

    // --- REAL DATA FOR STEP 3 ---
    // Load recorded data from localStorage
    const savedDataStr = localStorage.getItem('dissonanceData');
    if (savedDataStr) {
        const savedData = JSON.parse(savedDataStr);
        savedData.forEach(point => {
            addDataPoint(point.time, point.value, point.alert_level, point.face, point.voice, point.quadrant_face);
        });
        
        // Optional: clear local storage so the next session starts fresh
        // localStorage.removeItem('dissonanceData');
    } else {
        // Fallback or empty state
        console.log("No data recorded during session.");
    }

    // Button interactions
    document.getElementById('btn-close').addEventListener('click', () => {
        window.electronAPI.closeApp();
    });

    document.getElementById('btn-save').addEventListener('click', () => {
        const notes = document.getElementById('clinical-notes').value;
        const btn = document.getElementById('btn-save');
        
        if (notes.trim() === '') {
            btn.innerText = "Ajoutez des notes d'abord";
            btn.style.backgroundColor = 'var(--accent-red)';
            setTimeout(() => {
                btn.innerText = "Enregistrer le compte-rendu";
                btn.style.backgroundColor = 'var(--accent-green)';
            }, 2000);
            return;
        }

        // Alert animation effect
        const originalText = btn.innerText;
        btn.innerText = "✓ Enregistré";
        btn.style.backgroundColor = 'rgba(222, 255, 154, 0.5)';
        setTimeout(() => {
            btn.innerText = originalText;
            btn.style.backgroundColor = 'var(--accent-green)';
        }, 2000);
    });
});
