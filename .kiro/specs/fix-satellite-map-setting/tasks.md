# Implementation Plan

- [ ] 1. Create maps settings API endpoint
  - [ ] 1.1 Add maps settings data model to settings profile
    - Extend MapsSettings model to include style field with validation
    - Add style field with enum validation for standard/satellite/hybrid/terrain
    - _Requirements: 1.1, 2.1, 3.1_

  - [ ] 1.2 Implement /api/v2/settings/maps GET endpoint
    - Create REST endpoint to retrieve current maps settings
    - Return provider, style, google_api_key, and other map configuration
    - Add proper ETag and caching headers for performance
    - _Requirements: 1.2, 3.2_

  - [ ] 1.3 Implement /api/v2/settings/maps PUT endpoint
    - Create REST endpoint to update maps settings
    - Validate style values against allowed enum (standard/satellite/hybrid/terrain)
    - Support partial updates while preserving existing settings
    - _Requirements: 1.1, 3.1, 3.3_

- [ ] 2. Fix frontend data flow integration
  - [ ] 2.1 Update MapsView to handle API errors gracefully
    - Add error handling for failed settings API calls
    - Provide fallback default settings when API is unavailable
    - Display user-friendly error messages
    - _Requirements: 2.4, 3.2_

  - [ ] 2.2 Ensure BoundaryEditor receives updated settings
    - Verify mapStyle prop is properly passed from MapsView settings
    - Test that tile layer switching works when settings change
    - _Requirements: 1.3, 2.3_

- [ ] 3. Add settings UI for satellite toggle
  - [ ] 3.1 Create map style selector in settings interface
    - Add dropdown or toggle for satellite/standard/hybrid/terrain styles
    - Integrate with existing maps settings API endpoints
    - _Requirements: 1.1, 1.2_

  - [ ] 3.2 Add real-time preview of style changes
    - Update map display immediately when style setting changes
    - Show loading states during tile layer transitions
    - _Requirements: 1.3, 2.3_