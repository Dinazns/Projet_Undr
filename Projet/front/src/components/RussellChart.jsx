import { useEffect, useRef } from 'react'
import {
  Chart,
  ScatterController,
  PointElement,
  LinearScale,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js'

Chart.register(ScatterController, PointElement, LinearScale, LineElement, Tooltip, Legend)

/**
 * Mapping de Russell : place le visage et la voix dans le plan circumplexe
 * (Valence en X, Arousal en Y, de -1 à +1) pour visualiser l'écart détecté.
 *
 * Props :
 *  - entry : { face_coords: [v, a], voice_coords: [v, a], face, voice }
 *            L'un des deux points peut être absent (null).
 */
export default function RussellChart({ entry }) {
  const canvasRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!canvasRef.current) return
    const ctx = canvasRef.current.getContext('2d')

    const faceC = entry?.face_coords
    const voiceC = entry?.voice_coords

    const datasets = []
    if (faceC && Array.isArray(faceC) && faceC.length === 2) {
      datasets.push({
        label: `Visage${entry?.face ? ` (${entry.face})` : ''}`,
        data: [{ x: faceC[0], y: faceC[1] }],
        backgroundColor: '#deff9a',
        borderColor: '#9bd400',
        pointRadius: 8,
        pointHoverRadius: 10,
      })
    }
    if (voiceC && Array.isArray(voiceC) && voiceC.length === 2) {
      datasets.push({
        label: `Voix${entry?.voice ? ` (${entry.voice})` : ''}`,
        data: [{ x: voiceC[0], y: voiceC[1] }],
        backgroundColor: '#ff8c5c',
        borderColor: '#ff5c5c',
        pointRadius: 8,
        pointHoverRadius: 10,
      })
    }

    // Ligne reliant les deux points si les deux existent (visualise l'écart)
    if (
      faceC && Array.isArray(faceC) && faceC.length === 2 &&
      voiceC && Array.isArray(voiceC) && voiceC.length === 2
    ) {
      datasets.push({
        label: 'Incongruence (visage ↔ voix)',
        data: [
          { x: faceC[0], y: faceC[1] },
          { x: voiceC[0], y: voiceC[1] },
        ],
        type: 'line',
        borderColor: 'rgba(255,255,255,0.35)',
        borderWidth: 1,
        borderDash: [5, 5],
        pointRadius: 0,
        fill: false,
        showLine: true,
      })
    }

    chartRef.current = new Chart(ctx, {
      type: 'scatter',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: 8 },
        plugins: {
          legend: {
            labels: { color: 'rgba(255,255,255,0.75)' },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const p = ctx.raw
                return `${ctx.dataset.label} : V=${p.x?.toFixed(2)}, A=${p.y?.toFixed(2)}`
              },
            },
          },
        },
        scales: {
          x: {
            min: -1,
            max: 1,
            title: { display: true, text: 'Valence (− négatif → + positif)', color: 'rgba(255,255,255,0.6)' },
            grid: { color: (c) => (c.tick.value === 0 ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.08)') },
            ticks: { color: 'rgba(255,255,255,0.6)', stepSize: 0.5 },
          },
          y: {
            min: -1,
            max: 1,
            title: { display: true, text: 'Arousal (− calme → + actif)', color: 'rgba(255,255,255,0.6)' },
            grid: { color: (c) => (c.tick.value === 0 ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.08)') },
            ticks: { color: 'rgba(255,255,255,0.6)', stepSize: 0.5 },
          },
        },
      },
    })

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy()
        chartRef.current = null
      }
    }
  }, [entry])

  return <canvas ref={canvasRef} />
}