import { useEffect, useCallback, useRef } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '../store/store';
import { webSocketService } from '../services/websocket';
import { setConnectionState, setStatus } from '../store/slices/mowerSlice';

interface UseWebSocketOptions {
  reconnectOnMount?: boolean;
  autoConnect?: boolean;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  connectionState: 'connected' | 'disconnected' | 'connecting' | 'error';
  connect: () => void;
  disconnect: () => void;
  send: (topic: string, data: any) => void;
  sendCommand: (command: string, parameters?: any) => Promise<any>;
  subscribe: (callback: (data: any) => void, event?: string) => () => void;
}

export const useWebSocket = (
  url?: string, 
  options: UseWebSocketOptions = {}
): UseWebSocketReturn => {
  const { reconnectOnMount = true, autoConnect = true } = options;
  const dispatch = useDispatch();
  const isConnected = useSelector((state: RootState) => state.mower.isConnected);
  const callbacksRef = useRef<Map<string, Function[]>>(new Map());

  const connect = useCallback(() => {
    webSocketService.connect();
  }, []);

  const disconnect = useCallback(() => {
    webSocketService.disconnect();
    dispatch(setConnectionState(false));
  }, [dispatch]);

  const send = useCallback((topic: string, data?: any) => {
    webSocketService.send({ type: topic, data });
  }, []);

  const sendCommand = useCallback((command: string, parameters?: any) => {
    return webSocketService.sendCommand(command, parameters);
  }, []);

  const subscribe = useCallback((callback: (data: any) => void, event: string = 'message') => {
    if (!callbacksRef.current.has(event)) {
      callbacksRef.current.set(event, []);
    }
    callbacksRef.current.get(event)!.push(callback);
    
    webSocketService.on(event, callback);

    // Return unsubscribe function
    return () => {
      webSocketService.off(event, callback);
      const callbacks = callbacksRef.current.get(event);
      if (callbacks) {
        const index = callbacks.indexOf(callback);
        if (index > -1) {
          callbacks.splice(index, 1);
        }
      }
    };
  }, []);

  // Setup WebSocket event listeners
  useEffect(() => {
    const handleConnect = () => {
      dispatch(setConnectionState(true));
    };

    const handleDisconnect = () => {
      dispatch(setConnectionState(false));
    };

    const handleMowerStatus = (data: any) => {
      dispatch(setStatus(data));
    };

    const handleError = (error: any) => {
      console.error('WebSocket error:', error);
      dispatch(setConnectionState(false));
    };

    // Subscribe to WebSocket events
    webSocketService.on('connect', handleConnect);
    webSocketService.on('disconnect', handleDisconnect);
    webSocketService.on('mower_status', handleMowerStatus);
    webSocketService.on('error', handleError);

    // Auto-connect if enabled
    if (autoConnect && !isConnected) {
      connect();
    }

    // Cleanup on unmount
    return () => {
      webSocketService.off('connect', handleConnect);
      webSocketService.off('disconnect', handleDisconnect);
      webSocketService.off('mower_status', handleMowerStatus);
      webSocketService.off('error', handleError);
      
      // Clear all callbacks
      callbacksRef.current.clear();
    };
  }, [dispatch, autoConnect, isConnected, connect]);

  // Reconnect on mount if enabled
  useEffect(() => {
    if (reconnectOnMount && !isConnected) {
      const timer = setTimeout(() => {
        connect();
      }, 1000);
      
      return () => clearTimeout(timer);
    }
  }, [reconnectOnMount, isConnected, connect]);

  return {
    isConnected,
    connectionState: webSocketService.connectionState,
    connect,
    disconnect,
    send,
    sendCommand,
    subscribe,
  };
};

// Alternative hook for simple connection status checking
export const useWebSocketStatus = () => {
  const isConnected = useSelector((state: RootState) => state.mower.isConnected);
  return {
    isConnected,
    connectionState: webSocketService.connectionState,
  };
};

export default useWebSocket;
