import { useEffect, useRef } from 'react'
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import zoomPlugin from 'chartjs-plugin-zoom'

Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip,
  Legend,
  Filler,
  zoomPlugin
)

const ALERT_COLORS = {
  SEVERE: '#ff5c5c',
  MODERATE: '#ffa500',
  VIGILANCE: '#ffff00',
  NONE: '#deff9a',
}

const ALERT_RADIUS = {
  SEVERE: 6,
  MODERATE: 5,
  VIGILANCE: 4,
  NONE: 0,
}

export default function DissonanceChart({ data }) {
  const canvasRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!canvasRef.current) return

    const ctx = canvasRef.current.getContext('2d')

    const labels = data.map((d) => d.time)
    const values = data.map((d) => ({
      x: d.time,
      y: d.value,
      face: d.face,
      voice: d.voice,
    }))

    const pointColors = data.map((d) => ALERT_COLORS[d.alert_level] || ALERT_COLORS.NONE)
    const pointRadii = data.map((d) => ALERT_RADIUS[d.alert_level] || ALERT_RADIUS.NONE)

    chartRef.current = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Niveau de Dissonance',
            data: values,
            borderColor: '#deff9a',
            backgroundColor: 'rgba(222, 255, 154, 0.1)',
            borderWidth: 2,
            tension: 0.4,
            fill: true,
            pointBackgroundColor: pointColors,
            pointBorderColor: 'transparent',
            pointRadius: pointRadii,
            pointHoverRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
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
              title: (context) => context[0].label,
              label: (context) => {
                const raw = context.raw
                return [
                  `Dissonance : ${context.parsed.y}%`,
                  `Visage : ${raw.face || 'N/A'}`,
                  `Voix : ${raw.voice || 'N/A'}`,
                ]
              },
            },
          },
          zoom: {
            zoom: {
              wheel: { enabled: true },
              pinch: { enabled: true },
              mode: 'x',
            },
            pan: {
              enabled: true,
              mode: 'x',
            },
          },
        },
        scales: {
          x: {
            grid: {
              color: 'rgba(255, 255, 255, 0.05)',
              drawBorder: false,
            },
            ticks: { maxTicksLimit: 10 },
          },
          y: {
            min: 0,
            max: 100,
            grid: {
              color: 'rgba(255, 255, 255, 0.05)',
              drawBorder: false,
            },
            ticks: {
              stepSize: 25,
              callback: (value) => value + '%',
            },
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
  }, [data])

  return <canvas ref={canvasRef} />
}
