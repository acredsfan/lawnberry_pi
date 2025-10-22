import type { Page, Request, Route } from '@playwright/test'

export interface WebSocketScriptEntry {
  /** Delay before dispatching message after socket opens (ms) */
  delayMs?: number
  /** JSON serialisable message delivered to the client */
  message: Record<string, unknown>
}

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'

interface MockRequestLogEntry {
  method: HttpMethod
  path: string
  body?: any
}

interface ManualUnlockState {
  sessionId: string
  expiresAt: string
}

export interface DriveCommandResult {
  result: 'ok' | 'blocked' | 'error'
  status_reason?: string
  remediation_link?: string
}

const jsonHeaders = {
  'content-type': 'application/json; charset=utf-8',
}

export class MockBackend {
  private requestLog: MockRequestLogEntry[] = []

  private manualUnlockSession: ManualUnlockState | null = null

  private wsScript: WebSocketScriptEntry[] = []

  private driveResult: DriveCommandResult = { result: 'ok' }

  private mapConfiguration: any = {
    config_id: 'default',
    config_version: 1,
    provider: 'osm',
    provider_metadata: {},
    boundary_zone: null,
    exclusion_zones: [] as any[],
    mowing_zones: [] as any[],
    markers: [] as any[],
    center_point: { latitude: 37.7749, longitude: -122.4194 },
    zoom_level: 18,
    map_rotation_deg: 0,
    validation_errors: [] as string[],
    last_modified: new Date().toISOString(),
    created_at: new Date().toISOString(),
  }

  private telemetryState: any = {
    battery: {
      percentage: 87.5,
      voltage: 12.6,
    },
    position: {
      latitude: 37.7749,
      longitude: -122.4194,
      accuracy: 0.7,
      hdop: 0.9,
      satellites: 14,
      rtk_status: 'FIX',
      speed: 0.6,
    },
    environmental: {
      temperature_c: 24.2,
      humidity_percent: 55.1,
      pressure_hpa: 1007.3,
      altitude_m: 18.4,
    },
    solar: {
      power: 180.5,
      voltage: 28.1,
      current: 6.1,
    },
    tof: {
      left: { distance_mm: 320, status: 'valid' },
      right: { distance_mm: 340, status: 'valid' },
    },
    imu: {
      calibration: 3,
      calibration_status: 'good',
    },
    motor_status: 'running',
    telemetry_source: 'hardware',
    safety_state: 'nominal',
  }

  private dashboardStatus = {
    status: 'Active',
    uptime: '2h 15m',
  }

  private weatherSnapshot = {
    temperature_c: 24.5,
    humidity_percent: 58,
    wind_speed_mps: 2.1,
    condition: 'Sunny',
    source: 'simulated',
    ts: new Date().toISOString(),
  }

  private settingsState = {
    system: {
      device_name: 'LawnBerry Pi',
      timezone: 'UTC',
      ui: { unit_system: 'metric' },
      debug_mode: false,
    },
    security: {
      auth_level: 'password',
      session_timeout_minutes: 15,
      require_https: false,
      auto_lock_manual_control: true,
    },
    remote: {
      method: 'none',
      enabled: false,
      cloudflare_token: '',
      ngrok_token: '',
      custom_domain: '',
      auto_tls: false,
    },
    maps: {
      provider: 'osm',
      google_api_key: '',
      google_billing_warnings: true,
      style: 'standard',
    },
    gps: {
      gps_loss_policy: 'stop',
      dead_reckoning_duration_minutes: 2,
      reduced_speed_factor: 0.5,
      accuracy_threshold_meters: 2,
    },
  }

  private hardwareSnapshot: any = {
    telemetry_source: 'hardware',
    safety_state: 'nominal',
    battery: { percentage: 87.5, voltage: 12.6 },
    position: { latitude: 37.7749, longitude: -122.4194 },
    velocity: { linear: { x: 0.45 } },
    camera: { active: true, mode: 'rtsp', fps: 20, client_count: 1 },
  }

  private trainingDataset = {
    totals: {
      images: 1247,
      labeled: 892,
      dataset_bytes: 245.7 * 1024 * 1024,
      accuracy: 94.2,
    },
    categories: [
      { name: 'grass', count: 456, labeled: 398 },
      { name: 'obstacles', count: 234, labeled: 187 },
    ],
  }

  public readonly emergencyCalls: any[] = []

  public readonly driveCommands: any[] = []

  public lastSavedConfiguration: any = null

  public readonly trainingRequests: any[] = []

  private applyMapEnvelope(env: any) {
    const zones = Array.isArray(env?.zones) ? env.zones : []
    const decodePolygon = (geometry: any) => {
      const coordinates = geometry?.coordinates?.[0]
      if (!Array.isArray(coordinates)) return []
      return coordinates
        .filter((pair: any) => Array.isArray(pair) && pair.length >= 2)
        .map(([lng, lat]: [number, number]) => ({ latitude: lat, longitude: lng }))
        .filter((point: any, index: number, arr: any[]) => {
          if (!point) return false
          // Drop duplicated closing coordinate if present
          if (index === arr.length - 1 && arr.length > 1) {
            const first = arr[0]
            return !(Math.abs(first.latitude - point.latitude) < 1e-12 && Math.abs(first.longitude - point.longitude) < 1e-12)
          }
          return true
        })
    }

    const buildZone = (zone: any) => ({
      id: zone?.zone_id ?? zone?.name ?? `${zone?.zone_type ?? 'zone'}-${Date.now()}`,
      name: zone?.name ?? zone?.zone_id ?? 'Zone',
      zone_type: zone?.zone_type ?? 'mow',
      polygon: decodePolygon(zone?.geometry),
    })

    const boundaryZone = zones.find((z: any) => z?.zone_type === 'boundary')
    this.mapConfiguration.boundary_zone = boundaryZone ? buildZone(boundaryZone) : null

    this.mapConfiguration.exclusion_zones = zones
      .filter((z: any) => z?.zone_type === 'exclusion')
      .map(buildZone)

    this.mapConfiguration.mowing_zones = zones
      .filter((z: any) => z?.zone_type === 'mow')
      .map(buildZone)

    if (typeof env?.provider === 'string') {
      this.mapConfiguration.provider = env.provider === 'google-maps' ? 'google' : env.provider
    }

    if (Array.isArray(env?.markers)) {
      this.mapConfiguration.markers = env.markers.map((marker: any) => ({
        marker_id: marker?.marker_id ?? `marker-${Date.now()}`,
        marker_type: marker?.marker_type ?? 'custom',
        position: {
          latitude: marker?.position?.latitude ?? 0,
          longitude: marker?.position?.longitude ?? 0,
        },
        label: marker?.label ?? null,
        icon: marker?.icon ?? null,
        metadata: marker?.metadata ?? null,
        schedule: marker?.schedule ?? null,
        is_home: marker?.is_home ?? marker?.marker_type === 'home',
      }))
    }

    this.mapConfiguration.last_modified = new Date().toISOString()
  }

  setWebSocketScript(script: WebSocketScriptEntry[]) {
    this.wsScript = script
  }

  setTelemetry(telemetry: any) {
    this.telemetryState = { ...this.telemetryState, ...telemetry }
  }

  setDashboardStatus(status: any) {
    this.dashboardStatus = { ...this.dashboardStatus, ...status }
  }

  setDriveResult(result: DriveCommandResult) {
    this.driveResult = result
  }

  setHardwareSnapshot(snapshot: any) {
    this.hardwareSnapshot = { ...this.hardwareSnapshot, ...snapshot }
  }

  setMapConfiguration(partial: Partial<typeof this.mapConfiguration>) {
    this.mapConfiguration = { ...this.mapConfiguration, ...partial }
  }

  setTrainingDataset(summary: any) {
    this.trainingDataset = { ...this.trainingDataset, ...summary }
  }

  setMapSettings(partial: Partial<(typeof this.settingsState)['maps']>) {
    this.settingsState.maps = { ...this.settingsState.maps, ...partial }
  }

  async attach(page: Page) {
    await page.addInitScript((script) => {
      class FakeWebSocket {
        public onopen: ((event: any) => void) | null = null
        public onmessage: ((event: { data: string }) => void) | null = null
        public onclose: ((event: any) => void) | null = null
        public onerror: ((event: any) => void) | null = null
        public readyState = 0
        private readonly recordedMessages: string[] = []
	public readonly url: string
        private pendingMessages: Array<{ topic?: string; payload: string; delay: number }>

        constructor(url: string) {
          this.url = url
          this.pendingMessages = []
          const registry = (window as any).__FAKE_WEBSOCKETS__ || []
          registry.push(this)
          ;(window as any).__FAKE_WEBSOCKETS__ = registry
          setTimeout(() => {
            this.readyState = 1
            this.onopen?.({ target: this })
            for (const entry of script.messages) {
              const payload = JSON.stringify(entry.message)
              const delay = entry.delayMs ?? 0
              const topic = (entry.message as any)?.topic
              const event = (entry.message as any)?.event
              if (!topic || event === 'connection.established' || event === 'subscription.confirmed') {
                this.dispatch(payload, delay)
              } else {
                this.pendingMessages.push({ topic, payload, delay })
              }
            }
          }, script.handshakeDelayMs)
        }

        send(payload: string) {
          this.recordedMessages.push(payload)
          try {
            const parsed = JSON.parse(payload)
            if (parsed?.type === 'ping') {
              setTimeout(() => {
                this.onmessage?.({ data: JSON.stringify({ event: 'pong' }) })
              }, 10)
            }
            if (parsed?.type === 'subscribe') {
              const topic = parsed.topic
              const remaining: Array<{ topic?: string; payload: string; delay: number }> = []
              for (const entry of this.pendingMessages) {
                if (!topic || entry.topic === topic) {
                  this.dispatch(entry.payload, entry.delay)
                } else {
                  remaining.push(entry)
                }
              }
              this.pendingMessages = remaining
            }
          } catch (error) {
            console.warn('FakeWebSocket failed to parse payload', error)
          }
        }

        close() {
          this.readyState = 3
          this.onclose?.({})
        }

        get sentMessages() {
          return this.recordedMessages
        }

        private dispatch(payload: string, delay: number) {
          setTimeout(() => {
            this.onmessage?.({ data: payload })
          }, delay)
        }
      }

      ;(window as any).WebSocket = FakeWebSocket
    }, { messages: this.wsScript, handshakeDelayMs: 25 })

    await page.route('**/api/**', (route, request) => this.handleRequest(route, request))
  }

  getRequests(): MockRequestLogEntry[] {
    return [...this.requestLog]
  }

  private async handleRequest(route: Route, request: Request) {
    const { pathname, searchParams } = new URL(request.url())
    const method = request.method().toUpperCase() as HttpMethod

    const body = await this.safeParseBody(request)
    this.requestLog.push({ method, path: pathname, body })

    const respond = (status: number, payload: unknown) =>
      route.fulfill({ status, headers: jsonHeaders, body: JSON.stringify(payload) })

    // Authentication
    if (method === 'POST' && pathname === '/api/v2/auth/login') {
      if (body?.username === 'admin' && body?.password === 'admin') {
        return respond(200, {
          access_token: 'test-token',
          expires_in: 3600,
          user: { id: 'user-1', username: 'admin', role: 'admin' },
        })
      }
      return respond(401, { detail: 'Invalid credentials' })
    }

    if (method === 'POST' && pathname === '/api/v2/auth/logout') {
      return respond(200, { ok: true })
    }

    if (method === 'POST' && pathname === '/api/v2/auth/refresh') {
      return respond(200, { access_token: 'test-token', expires_in: 3600 })
    }

    if (method === 'GET' && pathname === '/api/v2/auth/profile') {
      return respond(200, { id: 'user-1', username: 'admin', role: 'admin' })
    }

    // Dashboard
    if (method === 'GET' && pathname === '/api/v2/dashboard/status') {
      return respond(200, this.dashboardStatus)
    }

    if (method === 'GET' && pathname === '/api/v2/dashboard/telemetry') {
      return respond(200, this.telemetryState)
    }

    if (method === 'GET' && pathname === '/api/v2/weather/current') {
      return respond(200, this.weatherSnapshot)
    }

    // Settings API
    if (method === 'GET' && pathname === '/api/v2/settings/system') {
      return respond(200, this.settingsState.system)
    }

    if (method === 'PUT' && pathname === '/api/v2/settings/system') {
      this.settingsState.system = { ...this.settingsState.system, ...body }
      return respond(200, { ok: true, data: this.settingsState.system })
    }

    if (method === 'GET' && pathname === '/api/v2/settings/security') {
      return respond(200, this.settingsState.security)
    }

    if (method === 'PUT' && pathname === '/api/v2/settings/security') {
      this.settingsState.security = { ...this.settingsState.security, ...body }
      return respond(200, { ok: true })
    }

    if (method === 'GET' && pathname === '/api/v2/settings/remote-access') {
      return respond(200, this.settingsState.remote)
    }

    if (method === 'PUT' && pathname === '/api/v2/settings/remote-access') {
      this.settingsState.remote = { ...this.settingsState.remote, ...body }
      return respond(200, { ok: true })
    }

    if (method === 'GET' && pathname === '/api/v2/settings/maps') {
      return respond(200, this.settingsState.maps)
    }

    if (method === 'PUT' && pathname === '/api/v2/settings/maps') {
      this.settingsState.maps = { ...this.settingsState.maps, ...body }
      return respond(200, { ok: true })
    }

    if (method === 'GET' && pathname === '/api/v2/settings/gps-policy') {
      return respond(200, this.settingsState.gps)
    }

    if (method === 'PUT' && pathname === '/api/v2/settings/gps-policy') {
      this.settingsState.gps = { ...this.settingsState.gps, ...body }
      return respond(200, { ok: true })
    }

    // Manual control security config reuses settings/security response
    if (method === 'POST' && pathname === '/api/v2/control/manual-unlock') {
      this.manualUnlockSession = {
        sessionId: `session-${Date.now()}`,
        expiresAt: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
      }
      return respond(200, {
        session_id: this.manualUnlockSession.sessionId,
        expires_at: this.manualUnlockSession.expiresAt,
      })
    }

    if (method === 'GET' && pathname === '/api/v2/control/manual-unlock/status') {
      return respond(200, {
        authorized: Boolean(this.manualUnlockSession),
        session_id: this.manualUnlockSession?.sessionId ?? null,
        expires_at: this.manualUnlockSession?.expiresAt ?? null,
      })
    }

    if (method === 'POST' && pathname === '/api/v2/control/emergency') {
      this.emergencyCalls.push({ at: Date.now(), body })
      return respond(200, { result: 'ok' })
    }

    if (method === 'POST' && pathname === '/api/v2/control/drive') {
      this.driveCommands.push(body)
      return respond(200, this.driveResult)
    }

    if (method === 'POST' && pathname === '/api/v2/control/blade') {
      return respond(200, { result: 'ok' })
    }

    if (method === 'POST' && pathname === '/api/v2/control/emergency-stop') {
      this.emergencyCalls.push({ at: Date.now(), body, type: 'legacy' })
      return respond(200, { result: 'ok' })
    }

    if (method === 'GET' && pathname === '/api/v2/hardware/robohat') {
      return respond(200, this.hardwareSnapshot)
    }

    if (method === 'POST' && pathname === '/api/v2/camera/start') {
      return respond(200, { started: true })
    }

    if (method === 'GET' && pathname === '/api/v2/camera/status') {
      return respond(200, {
        active: true,
        mode: 'rtsp',
        fps: 20,
        client_count: 1,
        last_frame: new Date().toISOString(),
      })
    }

    if (method === 'GET' && pathname === '/api/v2/camera/frame') {
      return respond(200, {
        frame_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
        capture_ts: new Date().toISOString(),
      })
    }

    if (method === 'GET' && pathname === '/api/v2/training/dataset') {
      return respond(200, this.trainingDataset)
    }

    if (method === 'POST' && pathname === '/api/v2/training/start') {
      this.trainingRequests.push({ type: 'start', payload: body })
      return respond(200, { ok: true, job_id: `train-${Date.now()}` })
    }

    if (pathname === '/api/v2/map/configuration' && method === 'GET') {
      const configId = searchParams.get('config_id') ?? 'default'
      return respond(200, { ...this.mapConfiguration, config_id: configId })
    }

    if (pathname === '/api/v2/map/configuration' && method === 'PUT') {
      this.lastSavedConfiguration = body
      this.applyMapEnvelope(body)
      return respond(200, { ok: true })
    }

    if (pathname === '/api/v2/maps/zones' && method === 'POST') {
      this.mapConfiguration.mowing_zones = Array.isArray(body?.polygons)
        ? body.polygons.map((poly: any, idx: number) => ({
            id: poly?.id ?? `zone-${idx}`,
            name: poly?.name ?? `Zone ${idx + 1}`,
            zone_type: 'mow',
            polygon: Array.isArray(poly?.points)
              ? poly.points.map((pt: any) => ({ latitude: pt?.lat ?? pt?.latitude, longitude: pt?.lon ?? pt?.longitude }))
              : [],
          }))
        : this.mapConfiguration.mowing_zones
      return respond(200, { ok: true })
    }

    if (pathname === '/api/v2/map/provider-fallback' && method === 'POST') {
      this.settingsState.maps.provider = 'osm'
      return respond(200, { success: true })
    }

    // Default fallback: succeed with empty payload
    return respond(200, {})
  }

  private async safeParseBody(request: Request) {
    if (request.method() === 'GET' || request.method() === 'HEAD') {
      return undefined
    }
    const raw = await request.postData()
    if (!raw) return undefined
    try {
      return JSON.parse(raw)
    } catch {
      return raw
    }
  }
}