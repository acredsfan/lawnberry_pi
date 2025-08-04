import { useEffect, useRef } from 'react'

export interface MapCenteringHookProps {
  onCenterRequest: (position: { lat: number; lng: number }) => void
}

export const useMapAutoCentering = (onCenterRequest: (position: { lat: number; lng: number }) => void) => {
  const handlerRef = useRef<((event: CustomEvent) => void) | null>(null)

  useEffect(() => {
    // Define the event handler
    const handleCenterMapEvent = (event: CustomEvent) => {
      if (event.detail?.position) {
        console.log('🎯 Auto-centering map on robot position:', event.detail.position)
        onCenterRequest(event.detail.position)
      }
    }

    // Store reference for cleanup
    handlerRef.current = handleCenterMapEvent

    // Add event listener for centering events from data service
    window.addEventListener('centerMapOnRobot', handleCenterMapEvent as EventListener)

    return () => {
      // Cleanup event listener
      if (handlerRef.current) {
        window.removeEventListener('centerMapOnRobot', handlerRef.current as EventListener)
      }
    }
  }, [onCenterRequest])
}

export default useMapAutoCentering
