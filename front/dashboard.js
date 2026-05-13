// Simulate some websocket data for the chart initially since Step 3 is FastAPI
// We will structure it so it's ready to receive data via ws://

document.addEventListener('DOMContentLoaded', () => {
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
                        label: function(context) {
                            return `Dissonance: ${context.parsed.y}%`;
                        }
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

    // Prepare WebSocket logic (To be connected in Step 3)
    function addDataPoint(time, value, isAlert) {
        const dataset = dissonanceChart.data.datasets[0];
        
        dissonanceChart.data.labels.push(time);
        dataset.data.push(value);

        // Styling points based on alert status
        if (isAlert) {
            dataset.pointBackgroundColor.push('#ff5c5c'); // Red accent
            dataset.pointRadius.push(6); // Larger point
            
            // Update counter
            totalAlerts++;
            alertCounter.innerText = `${totalAlerts} alerte(s)`;
            
            // Pulse effect on badge
            alertCounter.style.transform = 'scale(1.1)';
            setTimeout(() => {
                alertCounter.style.transform = 'scale(1)';
            }, 200);
        } else {
            dataset.pointBackgroundColor.push('#deff9a'); // Normal point
            dataset.pointRadius.push(0); // Hidden unless hover
        }

        // Keep only last 50 points to avoid clutter
        if (dissonanceChart.data.labels.length > 50) {
            dissonanceChart.data.labels.shift();
            dataset.data.shift();
            dataset.pointBackgroundColor.shift();
            dataset.pointRadius.shift();
        }

        dissonanceChart.update();
    }

    // --- REAL DATA FOR STEP 3 ---
    // Load recorded data from localStorage
    const savedDataStr = localStorage.getItem('dissonanceData');
    if (savedDataStr) {
        const savedData = JSON.parse(savedDataStr);
        savedData.forEach(point => {
            addDataPoint(point.time, point.value, point.isAlert);
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
