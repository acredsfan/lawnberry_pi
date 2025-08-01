# LawnBerry Pi Web UI Testing Strategy

This document outlines the comprehensive testing strategy implemented for the LawnBerry Pi web UI, focusing on user experience and reliability.

## Testing Framework Overview

### Technology Stack
- **Unit/Integration Tests**: Vitest + React Testing Library
- **E2E Tests**: Playwright
- **Type Safety**: TypeScript compiler checks
- **Coverage**: V8 coverage provider with 80% thresholds

## Test Structure

```
src/test/
├── setup.ts                    # Test configuration and mocks
├── integration/                # Integration tests for key workflows
│   ├── mapProviderSwitching.test.tsx
│   └── websocketConnection.test.tsx
├── components/                 # Component tests
│   └── ui.test.tsx            # UI component library tests
└── e2e/                       # End-to-end tests
    └── mapFunctionality.spec.ts
```

## Key Testing Areas

### 1. Integration Tests

#### Map Provider Switching (`mapProviderSwitching.test.tsx`)
- Tests switching between Google Maps and Leaflet
- Verifies auto-fallback functionality when providers fail
- Ensures user data preservation during provider changes
- Tests offline mode graceful handling
- Validates user preference persistence

#### WebSocket Connection (`websocketConnection.test.tsx`)
- Tests real-time connection establishment
- Verifies connection status display
- Tests graceful handling of connection loss
- Validates real-time mower status updates
- Tests emergency stop command transmission
- Verifies pattern update subscriptions
- Tests connection cleanup on unmount

### 2. Component Tests

#### UI Components (`ui.test.tsx`)
- Tests all custom UI wrapper components (Card, Badge, Progress, Button, Alert)
- Verifies Material-UI integration
- Tests component composition and nesting
- Validates accessibility features
- Tests event handling and user interactions

### 3. End-to-End Tests

#### Map Functionality (`mapFunctionality.spec.ts`)
- Cross-browser compatibility testing (Chrome, Firefox, Safari, Edge)
- Mobile responsive design validation
- Touch interaction testing on mobile devices
- Keyboard shortcut functionality
- Boundary creation and editing workflows
- No-go zone management
- Robot status display and battery monitoring
- Offline scenario handling

## Test Coverage Requirements

### Coverage Thresholds
- **Branches**: 80%
- **Functions**: 80%
- **Lines**: 80%
- **Statements**: 80%

### Excluded from Coverage
- Configuration files
- Test files themselves
- Type definitions
- Build artifacts
- Main entry point (main.tsx)

## Running Tests

### Local Development
```bash
# Run all tests with watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Run E2E tests
npm run test:e2e

# Run type checking
npm run test:type
```

### CI/CD Pipeline
```bash
# Run all tests for CI
npm run test:ci

# Run E2E tests headlessly
npm run test:e2e
```

## Cross-Browser Testing

### Desktop Browsers
- Chrome (latest)
- Firefox (latest)
- Safari (webkit)
- Microsoft Edge

### Mobile Browsers
- Mobile Chrome (Pixel 5)
- Mobile Safari (iPhone 12)

### Known Limitations
- Google Maps API has known issues with WebKit/Safari in testing environments
- Fallback to Leaflet is automatically tested for these scenarios

## Mocking Strategy

### External Dependencies
- **Google Maps API**: Comprehensive mock with all required methods
- **Leaflet**: Mock with essential map functionality
- **Socket.IO**: Mock WebSocket client with event simulation
- **Environment Variables**: Controlled test environment setup

### Browser APIs
- ResizeObserver
- IntersectionObserver
- matchMedia
- Touch events for mobile testing

## Test Data Management

### Redux Store Mocking
- Configurable initial state for different test scenarios
- Isolated store instances per test
- Realistic data shapes matching production

### Service Mocking
- WebSocket service with controllable connection states
- Map services with predictable responses
- Boundary/zone services with CRUD operations

## Performance Testing

### Metrics Tracked
- Test execution time
- Bundle size impact
- Memory usage during tests
- Network request simulation

### Optimization
- Parallel test execution where safe
- Minimal DOM rendering for unit tests
- Efficient test cleanup and teardown

## Accessibility Testing

### Features Tested
- Keyboard navigation
- Screen reader compatibility
- ARIA attributes
- Focus management
- Color contrast (where applicable)

## Continuous Integration

### GitHub Actions Integration
- Runs on push to main/develop branches
- Parallel execution of test suites
- Artifact collection for debugging
- Coverage reporting
- Cross-browser testing matrix

### Test Results
- JUnit XML format for CI integration
- HTML coverage reports
- Playwright test reports with screenshots/videos on failure

## Debugging and Troubleshooting

### Common Issues
1. **Async operations**: Use proper `waitFor` and `findBy` queries
2. **Map initialization**: Ensure proper mocking of map providers
3. **WebSocket connections**: Use controlled mock implementations
4. **Timing issues**: Prefer semantic queries over arbitrary timeouts

### Debug Tools
- Vitest UI for interactive debugging
- Playwright trace viewer for E2E issues
- React DevTools integration
- Redux DevTools for state inspection

## Best Practices

### Test Writing
- Focus on user behavior, not implementation details
- Use semantic queries (getByRole, getByLabelText)
- Test error states and edge cases
- Maintain test independence and isolation

### Maintenance
- Regular dependency updates
- Test refactoring alongside code changes
- Performance monitoring of test suite
- Documentation updates with new features

## Future Enhancements

### Planned Additions
- Visual regression testing
- Performance benchmarking
- Accessibility automation
- API contract testing
- Stress testing for real-time features

This testing strategy ensures high confidence in deployments, catches regressions early, and maintains excellent user experience across all supported platforms and browsers.
