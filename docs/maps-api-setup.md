# Maps API Configuration Guide

This guide covers setting up and configuring mapping services for LawnBerry Pi v2, including Google Maps API integration, OpenStreetMap fallback, and GPS policy configuration.

## Table of Contents

1. [Overview](#overview)
2. [Google Maps API Setup](#google-maps-api-setup)
3. [OpenStreetMap Configuration](#openstreetmap-configuration)
4. [GPS Policy Configuration](#gps-policy-configuration)
5. [Map Provider Management](#map-provider-management)
6. [Cost Management](#cost-management)
7. [Troubleshooting](#troubleshooting)

## Overview

LawnBerry Pi v2 supports multiple mapping providers with intelligent fallback and cost management:

- **Google Maps API**: Premium mapping with satellite imagery and detailed data
- **OpenStreetMap (OSM)**: Free, open-source mapping data
- **Hybrid Mode**: Google Maps primary with OSM fallback
- **Offline Mode**: Cached maps for areas without internet connectivity

### Key Features

- **Flexible Provider Selection**: Choose primary and fallback providers
- **Cost Controls**: API usage limits and monitoring
- **Offline Caching**: Store map data for offline operation
- **GPS Policy Management**: Configure dead reckoning and fallback behavior
- **User-Supplied API Keys**: Bring your own credentials for full control

## Google Maps API Setup

Google Maps provides the highest quality mapping data but requires API key setup and usage monitoring.

### Step 1: Create Google Cloud Project

1. **Go to Google Cloud Console**: [console.cloud.google.com](https://console.cloud.google.com)

2. **Create New Project**:
   - Click "Select a project" → "New Project"
   - Project name: "LawnBerry Pi Maps"
   - Note the Project ID

3. **Enable Billing**:
   - Go to Billing → Link a billing account
   - Google Maps APIs require billing enabled
   - Set up billing alerts for cost control

### Step 2: Enable Required APIs

Enable the following APIs for full functionality:

```bash
# Required APIs to enable:
# - Maps JavaScript API (for web interface)
# - Maps Static API (for static map images)
# - Geocoding API (for address resolution)
# - Places API (optional, for location search)
# - Roads API (optional, for precise positioning)
```

In Google Cloud Console:
1. **Go to APIs & Services** → **Library**
2. **Search and enable each API**:
   - Maps JavaScript API
   - Maps Static API
   - Geocoding API
   - Places API (optional)
   - Roads API (optional)

### Step 3: Create API Key

1. **Go to APIs & Services** → **Credentials**

2. **Create API Key**:
   - Click "Create Credentials" → "API Key"
   - Copy the API key (keep secure!)
   - Click "Restrict Key" for security

3. **Configure API Key Restrictions**:
   
   **Application Restrictions**:
   - Choose "HTTP referrers (web sites)"
   - Add your LawnBerry Pi domains:
     ```
     https://lawnberry.yourdomain.com/*
     https://your-pi-ip:3000/*
     http://localhost:3000/*  (for testing)
     ```

   **API Restrictions**:
   - Choose "Restrict key"
   - Select enabled APIs only:
     - Maps JavaScript API
     - Maps Static API
     - Geocoding API
     - Places API (if enabled)
     - Roads API (if enabled)

### Step 4: Configure LawnBerry Pi

```bash
# Configure Google Maps API
lawnberry-pi config maps --provider google \
    --api-key "YOUR_GOOGLE_MAPS_API_KEY" \
    --enable-satellite \
    --enable-street-view \
    --cache-tiles

# Set usage limits for cost control
lawnberry-pi config maps --google-limits \
    --daily-requests 10000 \
    --monthly-budget 50.00 \
    --alert-threshold 80

# Test configuration
lawnberry-pi config maps --test-google-api
```

### Step 5: Verify Setup

```bash
# Test Google Maps functionality
lawnberry-pi maps test --provider google --verbose

# Check API key status
lawnberry-pi maps status --show-quotas --show-usage

# Test specific features
lawnberry-pi maps test --geocoding "1600 Amphitheatre Parkway, Mountain View, CA"
lawnberry-pi maps test --static-map --lat 37.4219983 --lng -122.084
```

### Google Maps Features Configuration

```bash
# Enable advanced features
lawnberry-pi config maps --google-features \
    --enable-places-search \
    --enable-street-view \
    --enable-roads-api \
    --high-quality-imagery

# Configure map styles
lawnberry-pi config maps --google-style satellite  # satellite, roadmap, hybrid, terrain

# Set default zoom and center
lawnberry-pi config maps --default-zoom 18 \
    --center-lat YOUR_HOME_LAT \
    --center-lng YOUR_HOME_LNG
```

## OpenStreetMap Configuration

OpenStreetMap provides free mapping data without API keys or usage limits.

### Basic OSM Setup

```bash
# Configure OpenStreetMap as primary provider
lawnberry-pi config maps --provider osm \
    --tile-server "https://tile.openstreetmap.org/{z}/{x}/{y}.png" \
    --cache-tiles \
    --max-zoom 19

# Test OSM configuration
lawnberry-pi config maps --test-osm
```

### Alternative OSM Tile Servers

```bash
# Use different OSM tile servers for better performance/features

# OpenTopoMap (topographic style)
lawnberry-pi config maps --osm-server \
    "https://a.tile.opentopomap.org/{z}/{x}/{y}.png"

# Stamen Terrain
lawnberry-pi config maps --osm-server \
    "https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.png"

# CartoDB Positron (light style)
lawnberry-pi config maps --osm-server \
    "https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png"

# Satellite imagery (requires compatible server)
lawnberry-pi config maps --osm-server \
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
```

### Offline OSM Data

```bash
# Download OSM data for offline use
lawnberry-pi maps download-area \
    --north 40.7829 --south 40.7489 \
    --east -73.9441 --west -73.9927 \
    --zoom-min 10 --zoom-max 18

# Configure offline-first mode
lawnberry-pi config maps --offline-first \
    --cache-size 2GB \
    --cache-expiry 30  # 30 days
```

## GPS Policy Configuration

Configure GPS behavior, dead reckoning policies, and fallback procedures.

### Basic GPS Configuration

```bash
# Configure GPS device and basic settings
lawnberry-pi config gps --device /dev/ttyACM0 \
    --baud-rate 9600 \
    --update-rate 10  # 10Hz updates

# Set GPS accuracy requirements
lawnberry-pi config gps --accuracy-requirements \
    --horizontal-accuracy 2.0 \  # 2 meters
    --vertical-accuracy 5.0 \    # 5 meters
    --min-satellites 6
```

### Dead Reckoning Policy

Configure behavior when GPS signal is lost:

```bash
# Configure dead reckoning policy (FR-029)
lawnberry-pi config gps --dead-reckoning \
    --max-duration 120 \      # 2 minutes maximum
    --reduced-speed-factor 0.5 \  # 50% speed during dead reckoning
    --stop-on-timeout \       # Stop when dead reckoning expires
    --alert-on-timeout        # Send alert when GPS lost

# Configure GPS loss behavior
lawnberry-pi config gps --loss-policy \
    --immediate-action "reduce_speed" \
    --timeout-action "stop_and_alert" \
    --recovery-action "resume_normal"
```

### GPS Quality Monitoring

```bash
# Configure GPS quality monitoring
lawnberry-pi config gps --quality-monitoring \
    --track-accuracy \
    --log-satellites \
    --monitor-signal-strength \
    --alert-poor-quality

# Set quality thresholds
lawnberry-pi config gps --quality-thresholds \
    --min-satellites 4 \
    --max-hdop 2.0 \         # Horizontal dilution of precision
    --min-signal-strength -130  # dBm
```

### GPS Testing and Calibration

```bash
# Test GPS functionality
lawnberry-pi gps test --duration 300  # 5 minute test

# Check GPS status
lawnberry-pi gps status --show-satellites --show-accuracy

# Calibrate GPS with known position
lawnberry-pi gps calibrate --known-lat 40.7128 --known-lng -74.0060

# View GPS logs
lawnberry-pi gps logs --tail 100 --show-quality
```

## Map Provider Management

Configure multiple providers with intelligent switching and fallback policies.

### Hybrid Configuration

```bash
# Configure Google Maps primary with OSM fallback
lawnberry-pi config maps --hybrid-mode \
    --primary google \
    --fallback osm \
    --auto-switch-on-quota \
    --auto-switch-on-error

# Set switching thresholds
lawnberry-pi config maps --switch-thresholds \
    --error-rate 10 \        # Switch after 10% error rate
    --quota-threshold 90 \   # Switch at 90% quota usage
    --response-time 5000     # Switch if response > 5 seconds
```

### Provider Priorities

```bash
# Configure provider priority order
lawnberry-pi config maps --provider-priority \
    google \     # First choice
    osm \        # Second choice
    offline      # Last resort

# Configure per-feature providers
lawnberry-pi config maps --feature-providers \
    --static-maps google \
    --geocoding google \
    --tile-server osm \
    --satellite google
```

### Cost-Based Switching

```bash
# Configure cost-based provider switching
lawnberry-pi config maps --cost-management \
    --daily-budget 10.00 \
    --switch-to-free-at 80 \  # Switch to free provider at 80% budget
    --reset-monthly

# Monitor costs and usage
lawnberry-pi maps costs --this-month --by-provider
lawnberry-pi maps usage --daily --show-quotas
```

## Cost Management

Control and monitor mapping API costs with built-in limits and alerts.

### Usage Monitoring

```bash
# View current usage statistics
lawnberry-pi maps usage --summary
lawnberry-pi maps usage --detailed --this-month

# Set up usage alerts
lawnberry-pi config maps --usage-alerts \
    --daily-limit 1000 \
    --monthly-limit 25000 \
    --alert-email admin@yourdomain.com
```

### Budget Controls

```bash
# Set strict budget limits
lawnberry-pi config maps --budget-controls \
    --monthly-budget 100.00 \
    --daily-budget 5.00 \
    --auto-disable-at-limit \
    --switch-to-free-at 80

# Configure budget alerts
lawnberry-pi config maps --budget-alerts \
    --alert-at 50 \  # Alert at 50% budget
    --alert-at 80 \  # Alert at 80% budget
    --alert-at 95    # Alert at 95% budget
```

### Usage Optimization

```bash
# Enable usage optimization features
lawnberry-pi config maps --optimize-usage \
    --cache-aggressively \
    --batch-requests \
    --compress-images \
    --reduce-update-frequency

# Configure caching policy
lawnberry-pi config maps --caching \
    --tile-cache-size 1GB \
    --geocode-cache-size 100MB \
    --cache-ttl 86400  # 24 hours
```

### Cost Analysis

```bash
# Analyze costs by feature
lawnberry-pi maps costs --by-feature --this-month

# Compare provider costs
lawnberry-pi maps costs --compare-providers

# Generate cost report
lawnberry-pi maps report --costs --usage --recommendations
```

## Advanced Configuration

### Custom Map Styles

```bash
# Configure custom Google Maps styles
lawnberry-pi config maps --google-style-json /path/to/style.json

# Or use predefined styles
lawnberry-pi config maps --google-style \
    retro \      # Retro style
    dark \       # Dark mode
    night \      # Night mode
    aubergine    # Aubergine style
```

### Geofencing Integration

```bash
# Configure geofencing with maps
lawnberry-pi config maps --geofencing \
    --enable-boundary-alerts \
    --visual-boundaries \
    --boundary-colors "red,blue,green"

# Set up restricted areas
lawnberry-pi maps geofence --add-restricted-area \
    --name "flower_bed" \
    --coordinates "lat1,lng1;lat2,lng2;lat3,lng3"
```

### Performance Optimization

```bash
# Optimize map performance
lawnberry-pi config maps --performance \
    --preload-tiles \
    --background-updates \
    --lazy-loading \
    --image-compression 80

# Configure for low-bandwidth environments
lawnberry-pi config maps --low-bandwidth \
    --reduce-quality \
    --minimize-requests \
    --aggressive-caching
```

## Troubleshooting

### Common Issues

#### Google Maps API Issues

1. **API Key Not Working**:
   ```bash
   # Test API key directly
   curl "https://maps.googleapis.com/maps/api/geocode/json?address=test&key=YOUR_API_KEY"
   
   # Check API key restrictions
   lawnberry-pi maps debug --api-key-test
   
   # Verify enabled APIs in Google Cloud Console
   ```

2. **Quota Exceeded**:
   ```bash
   # Check current quota usage
   lawnberry-pi maps quota --check-all
   
   # Switch to fallback provider
   lawnberry-pi config maps --force-fallback
   
   # Increase quotas in Google Cloud Console
   ```

3. **Billing Issues**:
   ```bash
   # Check billing status
   lawnberry-pi maps billing --status
   
   # Verify billing account in Google Cloud Console
   # Ensure valid payment method is attached
   ```

#### GPS Issues

1. **GPS Not Acquiring Signal**:
   ```bash
   # Check GPS device connectivity
   lsusb | grep GPS
   dmesg | grep tty
   
   # Test GPS device directly
   sudo cat /dev/ttyACM0
   
   # Check antenna and positioning
   lawnberry-pi gps diagnose --antenna-test
   ```

2. **Poor GPS Accuracy**:
   ```bash
   # Check GPS quality metrics
   lawnberry-pi gps status --detailed
   
   # View satellite information  
   lawnberry-pi gps satellites --show-snr
   
   # Calibrate GPS receiver
   lawnberry-pi gps calibrate --auto
   ```

3. **Dead Reckoning Issues**:
   ```bash
   # Test dead reckoning configuration
   lawnberry-pi gps test-dead-reckoning --duration 180
   
   # Check IMU integration
   lawnberry-pi sensors test-imu --integration-test
   
   # Verify policy configuration
   lawnberry-pi config gps --show-dead-reckoning-policy
   ```

#### OpenStreetMap Issues

1. **Tile Loading Problems**:
   ```bash
   # Test OSM tile server connectivity
   lawnberry-pi maps test-osm --tile-test
   
   # Try alternative tile servers
   lawnberry-pi config maps --osm-server "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
   
   # Check tile cache
   lawnberry-pi maps cache --status --clear-corrupted
   ```

2. **Missing Map Data**:
   ```bash
   # Download missing area data
   lawnberry-pi maps download-area --auto-detect
   
   # Check offline cache status
   lawnberry-pi maps cache --status --show-coverage
   
   # Force cache refresh
   lawnberry-pi maps cache --refresh --area current
   ```

### Debug Commands

```bash
# Comprehensive maps diagnosis
lawnberry-pi maps diagnose --all

# Test all configured providers
lawnberry-pi maps test --all-providers --verbose

# Check network connectivity
lawnberry-pi network test --maps-apis

# View detailed logs
sudo journalctl -u lawnberry-backend | grep maps
```

### Performance Monitoring

```bash
# Monitor map performance
lawnberry-pi maps performance --real-time

# Check response times
lawnberry-pi maps latency --test-all-providers

# Monitor cache efficiency
lawnberry-pi maps cache --stats --hit-rate
```

### Configuration Validation

```bash
# Validate all maps configuration
lawnberry-pi config maps --validate --fix-issues

# Test configuration changes
lawnberry-pi config maps --test-changes --dry-run

# Backup/restore configuration
lawnberry-pi config backup --maps-only
lawnberry-pi config restore --maps-only --file maps-backup.json
```

## Best Practices

### Cost Optimization

1. **Use Hybrid Mode**: Combine Google Maps for critical features with OSM for routine operations
2. **Implement Caching**: Cache tiles and geocoding results aggressively
3. **Set Budget Limits**: Always configure budget alerts and automatic switching
4. **Monitor Usage**: Regular usage analysis to optimize API calls

### Performance Optimization

1. **Preload Common Areas**: Cache frequently used map areas
2. **Optimize Image Quality**: Balance quality vs. bandwidth/cost
3. **Use Appropriate Zoom Levels**: Don't fetch higher resolution than needed
4. **Batch Requests**: Combine multiple geocoding requests when possible

### Security Considerations

1. **Restrict API Keys**: Always use API key restrictions
2. **Monitor Usage**: Watch for unusual usage patterns
3. **Rotate Keys**: Periodically rotate API keys
4. **Network Security**: Use HTTPS for all map requests

For additional help with maps configuration, check the troubleshooting logs or run the built-in diagnostics tools.

## Security and secrets handling

- Do not commit API keys to the repository. The file `config/maps_settings.json` is now git-ignored and will be created/updated at runtime via the REST API (`PUT /api/v2/settings/maps`) or the UI Settings page.
- Use the UI or API to set `google_api_key`; it will be stored locally on the device only. For CI/dev samples, see `config/maps_settings.example.json`.
- The secrets store `config/secrets.json` is also git-ignored; the backend will auto-generate `JWT_SECRET` if missing. An example structure is provided in `config/secrets.example.json`.
- A pre-commit secret scan runs automatically when you install repo hooks (`./scripts/install-hooks.sh`) to prevent accidental leaks (Google keys, GitHub tokens, private keys, etc.).