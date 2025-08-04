import { MowerStatus } from '../types'

const API_BASE_URL = window.location.origin

export class DataService {
  private lastPosition: { lat: number; lng: number } | null = null
  private statusPollingInterval: number | null = null
  private subscribers: ((status: MowerStatus) => void)[] = []

  /**
   * Calculate distance between two GPS coordinates in miles
   */
  private calculateDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
    const R = 3959 // Earth's radius in miles
    const dLat = this.deg2rad(lat2 - lat1)
    const dLng = this.deg2rad(lng2 - lng1)
    const a = 
      Math.sin(dLat/2) * Math.sin(dLat/2) +
      Math.cos(this.deg2rad(lat1)) * Math.cos(this.deg2rad(lat2)) * 
      Math.sin(dLng/2) * Math.sin(dLng/2)
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a))
    return R * c
  }

  private deg2rad(deg: number): number {
    return deg * (Math.PI/180)
  }

  /**
   * Check if robot has moved more than 0.5 miles from last position
   */
  private shouldCenterMap(newPosition: { lat: number; lng: number }): boolean {
    if (!this.lastPosition) {
      this.lastPosition = newPosition
      return true // Center on first position
    }

    const distance = this.calculateDistance(
      this.lastPosition.lat,
      this.lastPosition.lng,
      newPosition.lat,
      newPosition.lng
    )

    if (distance > 0.5) {
      this.lastPosition = newPosition
      return true
    }

    return false
  }

  /**
   * Fetch current mower status from backend
   */
  async fetchMowerStatus(): Promise<MowerStatus> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/mock/status`)
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      
      // Check if we should trigger map centering
      if (data.position && this.shouldCenterMap(data.position)) {
        // Dispatch custom event for map centering
        window.dispatchEvent(new CustomEvent('centerMapOnRobot', {
          detail: { position: data.position }
        }))
      }
      
      return data
    } catch (error) {
      console.error('Failed to fetch mower status:', error)
      // Return fallback mock data
      return this.getFallbackStatus()
    }
  }

  /**
   * Fallback status when API is unavailable
   */
  private getFallbackStatus(): MowerStatus {
    return {
      state: 'idle',
      position: {
        lat: 40.7128,
        lng: -74.0060,
        heading: 0,
        accuracy: 5
      },
      battery: {
        level: 75.3,
        voltage: 24.1,
        current: 1.8,
        charging: false,
        timeRemaining: 120
      },
      sensors: {
        imu: {
          orientation: { x: 0, y: 0, z: 0 },
          acceleration: { x: 0, y: 0, z: 9.8 },
          gyroscope: { x: 0, y: 0, z: 0 },
          temperature: 35
        },
        tof: {
          left: 1.2,
          right: 1.5
        },
        environmental: {
          temperature: 22,
          humidity: 65,
          pressure: 1013
        },
        power: {
          voltage: 24.1,
          current: 1.8,
          power: 43.4
        }
      },
      coverage: {
        totalArea: 1000,
        coveredArea: 450,
        percentage: 45
      },
      lastUpdate: Date.now() / 1000,
      location_source: 'gps',
      connected: false
    }
  }

  /**
   * Start polling for mower status updates
   */
  startStatusPolling(intervalMs: number = 5000): void {
    if (this.statusPollingInterval) {
      this.stopStatusPolling()
    }

    this.statusPollingInterval = window.setInterval(async () => {
      try {
        const status = await this.fetchMowerStatus()
        this.notifySubscribers(status)
      } catch (error) {
        console.error('Status polling error:', error)
      }
    }, intervalMs)

    // Fetch initial status immediately
    this.fetchMowerStatus().then(status => {
      this.notifySubscribers(status)
    }).catch(error => {
      console.error('Initial status fetch error:', error)
    })
  }

  /**
   * Stop polling for status updates
   */
  stopStatusPolling(): void {
    if (this.statusPollingInterval) {
      clearInterval(this.statusPollingInterval)
      this.statusPollingInterval = null
    }
  }

  /**
   * Subscribe to status updates
   */
  subscribe(callback: (status: MowerStatus) => void): () => void {
    this.subscribers.push(callback)
    
    // Return unsubscribe function
    return () => {
      const index = this.subscribers.indexOf(callback)
      if (index > -1) {
        this.subscribers.splice(index, 1)
      }
    }
  }

  /**
   * Notify all subscribers of status update
   */
  private notifySubscribers(status: MowerStatus): void {
    this.subscribers.forEach(callback => {
      try {
        callback(status)
      } catch (error) {
        console.error('Subscriber callback error:', error)
      }
    })
  }

  /**
   * Check API connectivity
   */
  async checkConnectivity(): Promise<boolean> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/status`)
      return response.ok
    } catch {
      return false
    }
  }
}

// Export singleton instance
export const dataService = new DataService()
