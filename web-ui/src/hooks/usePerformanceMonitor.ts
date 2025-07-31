import { useEffect } from 'react'
import { useDispatch } from 'react-redux'
import { updatePerformanceMetrics } from '../store/slices/uiSlice'

export const usePerformanceMonitor = () => {
  const dispatch = useDispatch()

  useEffect(() => {
    let animationFrameId: number
    let lastTime = performance.now()
    let frameCount = 0
    const frameThreshold = 60 // Monitor every 60 frames

    const measurePerformance = () => {
      const currentTime = performance.now()
      frameCount++

      if (frameCount >= frameThreshold) {
        const renderTime = (currentTime - lastTime) / frameCount
        
        // Measure memory usage (if available)
        const memoryUsage = (performance as any).memory 
          ? (performance as any).memory.usedJSHeapSize / 1024 / 1024 
          : 0

        dispatch(updatePerformanceMetrics({
          renderTime: Math.round(renderTime * 100) / 100,
          memoryUsage: Math.round(memoryUsage * 100) / 100,
        }))

        frameCount = 0
        lastTime = currentTime
      }

      animationFrameId = requestAnimationFrame(measurePerformance)
    }

    // Start monitoring
    animationFrameId = requestAnimationFrame(measurePerformance)

    // Measure network latency periodically
    const measureNetworkLatency = async () => {
      try {
        const start = performance.now()
        const response = await fetch('/api/v1/ping', { 
          method: 'HEAD',
          cache: 'no-cache'
        })
        const end = performance.now()
        
        if (response.ok) {
          dispatch(updatePerformanceMetrics({
            networkLatency: Math.round(end - start)
          }))
        }
      } catch (error) {
        // Network error, set high latency
        dispatch(updatePerformanceMetrics({
          networkLatency: 9999
        }))
      }
    }

    const latencyInterval = setInterval(measureNetworkLatency, 30000) // Every 30 seconds

    return () => {
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId)
      }
      clearInterval(latencyInterval)
    }
  }, [dispatch])
}
