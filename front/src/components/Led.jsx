export default function Led({ color = 'green', label = '' }) {
  const colors = {
    green: '#deff9a',
    red: '#ff5c5c',
    orange: '#ffa500',
    yellow: '#ffff00',
  }

  const c = colors[color] || colors.green

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 600, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
      <div
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: c,
          boxShadow: `0 0 8px ${c}`,
        }}
      />
      {label && <span>{label}</span>}
    </div>
  )
}
