import { useEffect, useRef } from 'react'
import {
  Chart,
  DoughnutController,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js'
import { useI18n } from '../lib/i18n'

Chart.register(DoughnutController, ArcElement, Tooltip, Legend)

export default function ValenceChart({ positive, negative, neutral = 0 }) {
  const { t } = useI18n()
  const canvasRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!canvasRef.current) return

    const ctx = canvasRef.current.getContext('2d')

    chartRef.current = new Chart(ctx, {
      type: 'doughnut',
        data: {
          labels: [t('positive'), t('negative'), t('neutral')],
          datasets: [
            {
              data: [positive, negative, neutral],
              backgroundColor: ['#deff9a', '#ff5c5c', 'rgba(255, 255, 255, 0.25)'],
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
      }, [positive, negative, neutral, t])

  return <canvas ref={canvasRef} />
}
