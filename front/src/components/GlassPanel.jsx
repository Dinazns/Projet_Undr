export default function GlassPanel({ children, className = '', style = {} }) {
  return (
    <div
      className={className}
      style={{
        background: 'rgba(15, 15, 15, 0.65)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '16px',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
        color: '#fff',
        ...style,
      }}
    >
      {children}
    </div>
  )
}
