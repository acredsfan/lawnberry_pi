import React from 'react'

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
  info?: React.ErrorInfo
}

interface ErrorBoundaryProps {
  children: React.ReactNode
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    try {
      const existing = JSON.parse(localStorage.getItem('lbp_errors') || '[]')
      existing.push({ time: Date.now(), message: error.message, stack: error.stack, componentStack: info.componentStack })
      // Truncate to prevent unbounded growth
      while (existing.length > 25) existing.shift()
      localStorage.setItem('lbp_errors', JSON.stringify(existing))
    } catch (_) {}
    this.setState({ info })
  }

  render(): React.ReactNode {
    if (!this.state.hasError) return this.props.children
    return (
      <div style={{
        position: 'fixed', inset: 0, background: '#0a0a0a', color: '#FF1493', fontFamily: 'monospace',
        padding: '32px', zIndex: 99999, overflow: 'auto'
      }}>
        <h2 style={{ marginTop: 0 }}>UI Runtime Error</h2>
        <p>{this.state.error?.message}</p>
        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{this.state.error?.stack}</pre>
        {this.state.info?.componentStack && (
          <details>
            <summary>Component Trace</summary>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{this.state.info.componentStack}</pre>
          </details>
        )}
        <button onClick={() => window.location.reload()} style={{
          background: '#00FFD1', color: '#000', padding: '8px 16px', border: 'none', cursor: 'pointer', marginTop: 16
        }}>Reload</button>
      </div>
    )
  }
}

export default ErrorBoundary
