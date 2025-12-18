// @ts-nocheck
/**
 * Awaxen Real-Time Client - Socket.IO Entegrasyonu
 * 
 * Frontend (React/Next.js) için örnek kullanım.
 * 
 * Kurulum:
 *   npm install socket.io-client
 * 
 * Kullanım:
 *   import { useAwaxenSocket } from './realtime-client';
 *   
 *   const { isConnected, telemetry, prices } = useAwaxenSocket({
 *     userId: 'user-uuid',
 *     orgId: 'org-uuid',
 *     onDeviceStatus: (data) => console.log('Device status:', data),
 *   });
 */

import { io, Socket } from 'socket.io-client';
import { useEffect, useState, useCallback, useRef } from 'react';

// ==========================================
// Types
// ==========================================

interface TelemetryData {
  device_id: string;
  data: {
    power_w?: number;
    voltage?: number;
    current?: number;
    energy_total_kwh?: number;
    temperature?: number;
    humidity?: number;
    time?: string;
  };
  timestamp: string;
}

interface DeviceStatus {
  device_id: string;
  status: {
    is_online: boolean;
    last_seen: string;
    event?: string;
  };
  timestamp: string;
}

interface PriceUpdate {
  price: number;
  ptf?: number;
  smf?: number;
  hour: number;
  date: string;
  currency: string;
  timestamp: string;
}

interface Notification {
  id: string;
  title: string;
  message: string;
  type: 'info' | 'warning' | 'error' | 'success';
  timestamp: string;
}

interface AutomationEvent {
  automation_id: string;
  name: string;
  action: string;
  timestamp: string;
}

interface EnergySummary {
  total_consumption_kwh: number;
  total_cost: number;
  savings: number;
  active_devices: number;
  timestamp: string;
}

interface AwaxenSocketOptions {
  serverUrl?: string;
  userId: string;
  orgId?: string;
  token?: string;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onTelemetry?: (data: TelemetryData) => void;
  onDeviceStatus?: (data: DeviceStatus) => void;
  onPriceUpdate?: (data: PriceUpdate) => void;
  onNotification?: (data: Notification) => void;
  onAutomation?: (data: AutomationEvent) => void;
  onEnergySummary?: (data: EnergySummary) => void;
}

// ==========================================
// Socket Manager Class
// ==========================================

class AwaxenSocketManager {
  private socket: Socket | null = null;
  private options: AwaxenSocketOptions;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  constructor(options: AwaxenSocketOptions) {
    this.options = options;
  }

  connect(): void {
    const serverUrl = this.options.serverUrl || 'http://localhost:5000';
    
    this.socket = io(serverUrl, {
      transports: ['websocket', 'polling'],
      autoConnect: true,
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      auth: {
        token: this.options.token,
      },
    });

    this.setupEventHandlers();
  }

  private setupEventHandlers(): void {
    if (!this.socket) return;

    // Connection events
    this.socket.on('connect', () => {
      console.log('[Awaxen] Connected to real-time server');
      this.reconnectAttempts = 0;
      this.authenticate();
      this.options.onConnect?.();
    });

    this.socket.on('disconnect', (reason) => {
      console.log('[Awaxen] Disconnected:', reason);
      this.options.onDisconnect?.();
    });

    this.socket.on('connect_error', (error) => {
      console.error('[Awaxen] Connection error:', error);
      this.reconnectAttempts++;
    });

    // Authentication
    this.socket.on('authenticated', (data) => {
      console.log('[Awaxen] Authenticated:', data);
      this.subscribeToChannels();
    });

    this.socket.on('auth_error', (error) => {
      console.error('[Awaxen] Authentication error:', error);
    });

    // Real-time data events
    this.socket.on('telemetry', (data: TelemetryData) => {
      this.options.onTelemetry?.(data);
    });

    this.socket.on('device_status', (data: DeviceStatus) => {
      this.options.onDeviceStatus?.(data);
    });

    this.socket.on('device_update', (data: DeviceStatus) => {
      this.options.onDeviceStatus?.(data);
    });

    this.socket.on('price_update', (data: PriceUpdate) => {
      this.options.onPriceUpdate?.(data);
    });

    this.socket.on('notification', (data: Notification) => {
      this.options.onNotification?.(data);
    });

    this.socket.on('automation_triggered', (data: AutomationEvent) => {
      this.options.onAutomation?.(data);
    });

    this.socket.on('energy_summary', (data: EnergySummary) => {
      this.options.onEnergySummary?.(data);
    });

    this.socket.on('price_alert', (data) => {
      console.log('[Awaxen] Price alert:', data);
    });

    // Subscription confirmations
    this.socket.on('subscribed', (data) => {
      console.log('[Awaxen] Subscribed to:', data);
    });

    this.socket.on('room_joined', (data) => {
      console.log('[Awaxen] Joined room:', data);
    });

    // Heartbeat
    this.socket.on('pong', (data) => {
      console.debug('[Awaxen] Pong:', data.timestamp);
    });
  }

  private authenticate(): void {
    if (!this.socket) return;

    this.socket.emit('authenticate', {
      user_id: this.options.userId,
      org_id: this.options.orgId,
      token: this.options.token,
    });
  }

  private subscribeToChannels(): void {
    if (!this.socket) return;

    // Subscribe to price updates
    this.socket.emit('subscribe_prices');

    // Subscribe to dashboard updates
    if (this.options.orgId) {
      this.socket.emit('subscribe_dashboard', {
        org_id: this.options.orgId,
      });
    }
  }

  subscribeToDevice(deviceId: string): void {
    if (!this.socket) return;
    this.socket.emit('subscribe_device', { device_id: deviceId });
  }

  unsubscribeFromDevice(deviceId: string): void {
    if (!this.socket) return;
    this.socket.emit('unsubscribe_device', { device_id: deviceId });
  }

  ping(): void {
    if (!this.socket) return;
    this.socket.emit('ping');
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  isConnected(): boolean {
    return this.socket?.connected ?? false;
  }
}

// ==========================================
// React Hook
// ==========================================

export function useAwaxenSocket(options: AwaxenSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [telemetry, setTelemetry] = useState<Record<string, TelemetryData>>({});
  const [prices, setPrices] = useState<PriceUpdate | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [energySummary, setEnergySummary] = useState<EnergySummary | null>(null);
  
  const managerRef = useRef<AwaxenSocketManager | null>(null);

  useEffect(() => {
    const manager = new AwaxenSocketManager({
      ...options,
      onConnect: () => {
        setIsConnected(true);
        options.onConnect?.();
      },
      onDisconnect: () => {
        setIsConnected(false);
        options.onDisconnect?.();
      },
      onTelemetry: (data) => {
        setTelemetry((prev) => ({
          ...prev,
          [data.device_id]: data,
        }));
        options.onTelemetry?.(data);
      },
      onPriceUpdate: (data) => {
        setPrices(data);
        options.onPriceUpdate?.(data);
      },
      onNotification: (data) => {
        setNotifications((prev) => [data, ...prev].slice(0, 50));
        options.onNotification?.(data);
      },
      onEnergySummary: (data) => {
        setEnergySummary(data);
        options.onEnergySummary?.(data);
      },
    });

    manager.connect();
    managerRef.current = manager;

    // Heartbeat interval
    const pingInterval = setInterval(() => {
      manager.ping();
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      manager.disconnect();
    };
  }, [options.userId, options.orgId]);

  const subscribeToDevice = useCallback((deviceId: string) => {
    managerRef.current?.subscribeToDevice(deviceId);
  }, []);

  const unsubscribeFromDevice = useCallback((deviceId: string) => {
    managerRef.current?.unsubscribeFromDevice(deviceId);
  }, []);

  return {
    isConnected,
    telemetry,
    prices,
    notifications,
    energySummary,
    subscribeToDevice,
    unsubscribeFromDevice,
  };
}

// ==========================================
// Usage Example
// ==========================================

/*
// In your React component:

import { useAwaxenSocket } from '@/lib/realtime-client';

function Dashboard() {
  const { 
    isConnected, 
    telemetry, 
    prices, 
    notifications,
    energySummary,
    subscribeToDevice 
  } = useAwaxenSocket({
    serverUrl: process.env.NEXT_PUBLIC_API_URL,
    userId: user.id,
    orgId: user.organization_id,
    token: accessToken,
    onDeviceStatus: (data) => {
      // Handle device online/offline
      toast.info(`Device ${data.device_id} is now ${data.status.is_online ? 'online' : 'offline'}`);
    },
    onNotification: (data) => {
      // Show toast notification
      toast[data.type](data.message);
    },
  });

  // Subscribe to specific device when viewing its details
  useEffect(() => {
    if (selectedDeviceId) {
      subscribeToDevice(selectedDeviceId);
    }
  }, [selectedDeviceId]);

  return (
    <div>
      <div className="status">
        {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
      </div>
      
      {prices && (
        <div className="price-widget">
          Current Price: {prices.price} TL/kWh
        </div>
      )}
      
      {energySummary && (
        <div className="energy-summary">
          <p>Total: {energySummary.total_consumption_kwh} kWh</p>
          <p>Cost: {energySummary.total_cost} TL</p>
          <p>Savings: {energySummary.savings} TL</p>
        </div>
      )}
      
      {Object.entries(telemetry).map(([deviceId, data]) => (
        <div key={deviceId} className="device-telemetry">
          <h4>Device: {deviceId}</h4>
          <p>Power: {data.data.power_w} W</p>
          <p>Updated: {data.timestamp}</p>
        </div>
      ))}
    </div>
  );
}
*/

export { AwaxenSocketManager };
export type { 
  TelemetryData, 
  DeviceStatus, 
  PriceUpdate, 
  Notification, 
  AutomationEvent,
  EnergySummary,
  AwaxenSocketOptions 
};
