# Requirements Document

## Introduction

Fix the issue where the leaflet/OSM map on the maps endpoint is not honoring the satellite setting from the settings endpoint. The map should properly switch between standard and satellite view based on the user's configuration.

## Glossary

- **Maps_API**: The `/api/v2/settings/maps` REST endpoint that stores map configuration
- **MapsView**: The Vue.js component that displays the map editor interface
- **BoundaryEditor**: The Vue.js component that renders the interactive Leaflet map
- **Satellite_Setting**: The configuration option that determines whether to show satellite imagery or standard map tiles
- **OSM_Provider**: OpenStreetMap tile provider used as fallback when Google Maps is not available
- **Google_Provider**: Google Maps tile provider that supports satellite imagery

## Requirements

### Requirement 1

**User Story:** As a user, I want the map to display satellite imagery when I have enabled satellite view in settings, so that I can see aerial photos of my lawn area.

#### Acceptance Criteria

1. WHEN the user sets the map style to "satellite" in settings, THE Maps_API SHALL store this preference
2. WHEN the MapsView loads, THE MapsView SHALL retrieve the current satellite setting from Maps_API
3. WHEN satellite view is enabled, THE BoundaryEditor SHALL display satellite imagery tiles
4. WHEN satellite view is disabled, THE BoundaryEditor SHALL display standard map tiles
5. WHEN using Google_Provider with satellite setting, THE BoundaryEditor SHALL use Google satellite imagery

### Requirement 2

**User Story:** As a user, I want the satellite setting to work with both Google Maps and OSM providers, so that I can see satellite imagery regardless of which map provider is configured.

#### Acceptance Criteria

1. WHEN Google_Provider is configured with satellite setting, THE BoundaryEditor SHALL use Google satellite tiles
2. WHEN OSM_Provider is configured with satellite setting, THE BoundaryEditor SHALL use Esri satellite tiles as fallback
3. WHEN the map provider is changed, THE BoundaryEditor SHALL maintain the satellite setting preference
4. WHEN satellite imagery is unavailable, THE BoundaryEditor SHALL gracefully fallback to standard tiles

### Requirement 3

**User Story:** As a user, I want the satellite setting to persist across browser sessions, so that my preference is remembered when I return to the application.

#### Acceptance Criteria

1. WHEN the user changes the satellite setting, THE Maps_API SHALL persist the change to storage
2. WHEN the user reloads the page, THE MapsView SHALL load the previously saved satellite setting
3. WHEN the satellite setting is changed, THE BoundaryEditor SHALL immediately update the map display
4. WHEN multiple users access the system, THE Maps_API SHALL maintain per-user satellite preferences