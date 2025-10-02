/**
 * Settings types for LawnBerry Pi v2
 * Frontend types for settings management and documentation
 */

export interface SettingsProfile {
  profile_id: string;
  profile_version: string;
  profile_name: string;
  
  // Settings categories
  hardware: HardwareSettings;
  network: NetworkSettings;
  telemetry: TelemetrySettings;
  control: ControlSettings;
  maps: MapsSettings;
  camera: CameraSettings;
  ai: AISettings;
  system: SystemSettings;
  
  // Branding compliance
  branding_checksum: string | null;
  branding_assets_present: boolean;
  
  // Metadata
  persisted_to_sqlite: boolean;
  persisted_to_config_files: boolean;
  created_at: string;
  updated_at: string;
}

export interface HardwareSettings {
  [key: string]: any;  // Calibration values, channel mappings, etc.
}

export interface NetworkSettings {
  wifi_enabled: boolean;
  wifi_auto_reconnect: boolean;
  ethernet_enabled: boolean;
  ethernet_bench_only: boolean;
  connection_timeout_s: number;
  api_rate_limit_per_minute: number;
}

export interface TelemetrySettings {
  cadence_hz: number;  // 1-10 Hz
  latency_target_ms: number;
  stream_enabled: boolean;
  buffer_size: number;
  compression_enabled: boolean;
}

export interface ControlSettings {
  latency_budget_ms: number;
  watchdog_timeout_ms: number;
  safety_interlocks_enabled: boolean;
  manual_control_enabled: boolean;
  audit_trail_enabled: boolean;
}

export interface MapsSettings {
  provider: 'google_maps' | 'osm';
  enable_osm_fallback: boolean;
  satellite_view: boolean;
  show_grid: boolean;
  show_exclusion_zones: boolean;
  marker_icons_enabled: boolean;
}

export interface CameraSettings {
  resolution_width: number;
  resolution_height: number;
  framerate: number;
  format: string;
  quality: number;
  auto_exposure: boolean;
}

export interface AISettings {
  model_selection: string;
  accelerator: 'coral_usb' | 'hailo_hat' | 'cpu_only';
  confidence_threshold: number;
  inference_enabled: boolean;
  max_detections: number;
}

export interface SystemSettings {
  sim_mode_enabled: boolean;
  debug_mode: boolean;
  log_level: string;
  auto_backup: boolean;
  data_retention_days: number;
}

export interface DocumentationBundle {
  bundle_available: boolean;
  manifest: DocumentationManifest;
  download_url: string;
  stale_warning: string | null;
  offline_available: boolean;
}

export interface DocumentationManifest {
  generated_at: string;
  bundle_path: string;
  bundle_checksum: string;
  bundle_size_bytes: number;
  freshness_threshold_days: number;
  total_documents: number;
  stale_documents: number;
  offline_available: boolean;
  documents: DocumentInfo[];
}

export interface DocumentInfo {
  path: string;
  checksum: string;
  size_bytes: number;
  freshness: DocumentFreshness;
}

export interface DocumentFreshness {
  last_modified: string;
  age_days: number;
  is_fresh: boolean;
  warning: string | null;
}

export interface ValidationResult {
  valid: boolean;
  issues: string[];
  branding_checksum: string | null;
  branding_assets_present: boolean;
  profile_version: string;
}

export interface RemediationMetadata {
  message: string;
  docs_link: string;
  command?: string;
}

export interface SettingsError {
  error: string;
  validation_errors?: string[];
  remediation: RemediationMetadata;
}

export interface VerificationArtifact {
  artifact_id: string;
  type: 'telemetry_log' | 'ui_screencast' | 'doc_diff' | 'performance_report';
  location: string;
  created_by: string;
  created_at: string;
  summary: string;
  linked_requirements: string[];  // FR-XXX format
}
