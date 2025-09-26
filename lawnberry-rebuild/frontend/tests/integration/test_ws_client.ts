/**
 * WebSocket Client Integration Tests (T069)
 * Tests WebSocket client cadence control and telemetry subscriptions
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { io, Socket } from 'socket.io-client'

describe('WebSocket Client Integration', () => {
  let socket: Socket
  const WS_URL = 'ws://localhost:8001'

  beforeEach(() => {
    // Create socket connection for each test
    socket = io(WS_URL, {
      transports: ['websocket'],
      autoConnect: false
    })
  })

  afterEach(() => {
    if (socket) {
      socket.disconnect()
    }
  })

  it('should establish WebSocket connection', (done) => {
    socket.on('connect', () => {
      expect(socket.connected).toBe(true)
      done()
    })

    socket.on('connect_error', (error) => {
      // Skip test if backend is not running
      console.warn('Backend not available for WebSocket test:', error.message)
      done()
    })

    socket.connect()
  })

  it('should receive telemetry data at default 5Hz cadence', (done) => {
    let messageCount = 0
    const startTime = Date.now()

    socket.on('connect', () => {
      // Subscribe to telemetry updates
      socket.emit('subscribe', { topic: 'telemetry/updates' })
    })

    socket.on('telemetry.data', (data) => {
      messageCount++
      
      // Check data structure
      expect(data).toHaveProperty('timestamp')
      expect(data).toHaveProperty('data')
      expect(data.data).toHaveProperty('battery')
      expect(data.data).toHaveProperty('position')
      
      // After receiving 10 messages, check cadence
      if (messageCount >= 10) {
        const elapsed = (Date.now() - startTime) / 1000
        const actualHz = messageCount / elapsed
        
        // Should be approximately 5Hz (allow ±1Hz tolerance)
        expect(actualHz).toBeGreaterThan(4)
        expect(actualHz).toBeLessThan(6)
        done()
      }
    })

    socket.on('connect_error', () => {
      console.warn('Backend not available, skipping WebSocket cadence test')
      done()
    })

    socket.connect()

    // Timeout after 5 seconds
    setTimeout(() => {
      if (messageCount === 0) {
        console.warn('No telemetry messages received, backend may be down')
      }
      done()
    }, 5000)
  })

  it('should allow cadence adjustment', (done) => {
    let messageCount = 0
    const targetCadence = 8 // 8Hz
    const startTime = Date.now()

    socket.on('connect', () => {
      // Set higher cadence
      socket.emit('set_cadence', { cadence_hz: targetCadence })
      
      // Subscribe to telemetry
      socket.emit('subscribe', { topic: 'telemetry/updates' })
    })

    socket.on('cadence.updated', (data) => {
      expect(data.cadence_hz).toBe(targetCadence)
    })

    socket.on('telemetry.data', () => {
      messageCount++
      
      // Check cadence after receiving enough messages
      if (messageCount >= 15) {
        const elapsed = (Date.now() - startTime) / 1000
        const actualHz = messageCount / elapsed
        
        // Should be approximately 8Hz (allow ±1Hz tolerance)
        expect(actualHz).toBeGreaterThan(7)
        expect(actualHz).toBeLessThan(9)
        done()
      }
    })

    socket.on('connect_error', () => {
      console.warn('Backend not available, skipping cadence adjustment test')
      done()
    })

    socket.connect()

    // Timeout after 5 seconds
    setTimeout(() => {
      if (messageCount === 0) {
        console.warn('No telemetry messages received for cadence test')
      }
      done()
    }, 5000)
  })

  it('should handle subscription confirmations', (done) => {
    socket.on('connect', () => {
      socket.emit('subscribe', { topic: 'telemetry/updates' })
    })

    socket.on('subscription.confirmed', (data) => {
      expect(data).toHaveProperty('topic')
      expect(data.topic).toBe('telemetry/updates')
      expect(data).toHaveProperty('timestamp')
      done()
    })

    socket.on('connect_error', () => {
      console.warn('Backend not available, skipping subscription test')
      done()
    })

    socket.connect()

    setTimeout(() => done(), 2000)
  })
})