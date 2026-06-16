import { useEffect, useRef } from 'react'
import {
  Chart,
  DoughnutController,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js'

Chart.register(DoughnutController, ArcElement, Tooltip, Legend)

export default function ValenceChart({ positive, negative }) {
  const canvasRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!canvasRef.current) return

    const ctx = canvasRef.current.getContext('2d')

    chartRef.current = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Positif', 'Négatif'],
        datasets: [
          {
            data: [positive, negative],
            backgroundColor: ['#deff9a', 'rgba(255, 255, 255, 0.1)'],
            borderWidth: 0,
            hoverOffset: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: 'rgba(255, 255, 255, 0.6)' },
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
  }, [positive, negative])

  return <canvas ref={canvasRef} />
}
