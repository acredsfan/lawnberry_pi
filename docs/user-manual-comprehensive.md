# LawnBerryPi User Manual

**Version:** 1.0  
**Target Audience:** All user expertise levels  
**Last Updated:** December 2024

## Table of Contents

1. [Getting Started](#getting-started)
2. [System Overview](#system-overview)
3. [Web Interface Guide](#web-interface-guide)
4. [Mowing Operations](#mowing-operations)
5. [Maps and Boundaries](#maps-and-boundaries)
6. [Safety Features](#safety-features)
7. [Power Management](#power-management)
8. [Maintenance](#maintenance)
9. [Troubleshooting](#troubleshooting)
10. [Advanced Configuration](#advanced-configuration)

---

## Getting Started

### First Time Setup

1. **Hardware Assembly**
   - Ensure all sensors are properly connected
   - Verify power connections (30Ah battery, solar panel)
   - Check that RoboHAT is securely mounted
   - Confirm camera is positioned correctly

2. **Initial System Boot**
   - Power on the Raspberry Pi
   - Wait for all services to start (2-3 minutes)
   - Connect to the web interface at `http://lawnberry-pi.local:8000`

3. **Network Configuration**
   - Connect to your WiFi network via the settings page
   - Ensure internet connection for weather and map services
   - Configure API keys if not already set during installation

### Quick Start Checklist

- [ ] Hardware assembled and powered
- [ ] System connected to WiFi
- [ ] Web interface accessible
- [ ] Yard boundaries defined
- [ ] Home location set
- [ ] First mowing pattern selected

---

## System Overview

### Hardware Components

**Core Processing:**
- Raspberry Pi 4B 16GB - Main computer
- RoboHAT with RP2040 - Motor control and sensor interface
- OLED Display - Shows system status

**Navigation Sensors:**
- 2x Time of Flight (ToF) sensors - Obstacle detection
- RTK GPS - Precise positioning
- IMU (Inertial Measurement Unit) - Orientation and tilt detection
- Camera - Visual obstacle detection and navigation

**Environmental Monitoring:**
- BME280 sensor - Temperature, humidity, pressure
- Weather API integration - Real-time weather data

**Power System:**
- 30Ah LiFePO4 battery - Main power storage
- 30W solar panel - Renewable charging
- Power monitoring - Real-time consumption tracking

### Software Architecture

The system uses a microservices architecture with 11 independent services:
- **Hardware Interface** - Sensor communication
- **Safety System** - Comprehensive safety monitoring
- **Navigation** - Path planning and execution
- **Vision System** - Camera processing and obstacle detection
- **Power Management** - Battery and solar monitoring
- **Weather Service** - Weather integration and scheduling
- **Communication** - MQTT message handling
- **Web API** - REST endpoints and WebSocket
- **Data Management** - Caching and analytics
- **System Integration** - Service coordination
- **Location Service** - GPS and coordinate management

---

## Web Interface Guide

### Dashboard Overview

The dashboard is your central control center, displaying:

**System Status Panel:**
- Current operation mode (Idle, Mowing, Charging, etc.)
- Battery level with color-coded indicators
- Connection status for all services
- Weather conditions and mowing safety status

**Live Camera Feed:**
- Real-time view from the robot's camera
- Shows current field of view and detected objects
- Indicates obstacle detection status

**Sensor Data:**
- ToF sensor readings (obstacle distances)
- GPS coordinates and fix quality
- IMU data (tilt, orientation)
- Environmental conditions

**Quick Controls:**
- Emergency Stop (always accessible)
- Start/Stop mowing operations
- Return to home base
- Manual navigation controls

### Navigation Controls

**Basic Operation:**
- **Start Mowing:** Begins autonomous operation with selected pattern
- **Stop Mowing:** Safely stops current operation
- **Return Home:** Navigates back to charging/home location
- **Emergency Stop:** Immediate halt of all movement

**Manual Controls:**
- Directional movement (Forward, Backward, Left, Right)
- Speed adjustment
- Blade control (On/Off)
- Manual positioning for setup tasks

### Settings Configuration

**Units and Display:**
- Temperature: Celsius/Fahrenheit
- Distance: Metric/Imperial
- Time format: 12/24 hour

**Safety Parameters:**
- Obstacle detection sensitivity
- Maximum slope tolerance
- Weather-based operation limits
- Emergency contact notifications

**Performance Settings:**
- Autonomous mowing speed
- Pattern overlap percentage
- Battery conservation mode
- Charging schedule optimization

---

## Mowing Operations

### Selecting Mowing Patterns

**Available Patterns:**

1. **Parallel Lines**
   - Most efficient for rectangular lawns
   - Straight back-and-forth pattern
   - Configurable spacing and angle

2. **Checkerboard**
   - Creates alternating pattern
   - Good for avoiding wear patterns
   - Excellent grass health maintenance

3. **Spiral**
   - Works from outside toward center
   - Ideal for irregular shaped yards
   - Ensures complete coverage

4. **Waves**
   - Sinusoidal cutting pattern
   - Reduces soil compaction
   - Aesthetic appeal

5. **Crosshatch**
   - Dual-angle cutting
   - Superior grass health
   - Maximum coverage assurance

### Starting a Mowing Session

1. **Pre-Operation Checks:**
   - Verify battery level (minimum 30% recommended)
   - Check weather conditions
   - Ensure boundaries are properly set
   - Confirm no-go zones are active

2. **Pattern Selection:**
   - Navigate to the Patterns page
   - Select desired mowing pattern
   - Adjust pattern parameters if needed
   - Preview pattern on map

3. **Initiate Mowing:**
   - Click "Start Mowing" on dashboard
   - System performs safety checks
   - Mower navigates to starting position
   - Autonomous operation begins

### Monitoring Progress

**Real-Time Tracking:**
- Live position on Google Maps
- Mowing path visualization
- Coverage percentage
- Time remaining estimate
- Current activity status

**Performance Metrics:**
- Area covered per hour
- Battery consumption rate
- Obstacle encounters
- Safety system activations

---

## Maps and Boundaries

### Google Maps Integration

The system provides comprehensive Google Maps integration for intuitive yard management.

**Map Features:**
- Satellite imagery for precise boundary setting
- Interactive drawing tools
- Real-time robot tracking
- Offline mode capability
- Mobile-responsive touch controls

### Setting Yard Boundaries

1. **Access Maps Page:**
   - Navigate to "Maps" in the main menu
   - Ensure Google Maps is loaded and centered on your location

2. **Draw Boundary:**
   - Click the "Draw Boundary" tool in the toolbar
   - Click around the perimeter of your lawn
   - Create a polygon that encompasses the entire mowing area
   - Double-click to complete the boundary

3. **Edit Boundaries:**
   - Click on any boundary line to select
   - Drag corner points to adjust shape
   - Right-click to add new points
   - Delete points by selecting and pressing Delete

4. **Save Boundaries:**
   - Click "Save Boundary" when satisfied
   - Name your boundary (e.g., "Front Yard", "Back Lawn")
   - Boundaries are automatically saved to the system

### Creating No-Go Zones

No-go zones protect areas where the mower should never operate:

**Common No-Go Zone Uses:**
- Garden beds and flower areas
- Pool areas
- Children's play equipment
- Delicate landscaping
- Sprinkler heads
- Decorative features

**Creating No-Go Zones:**
1. Select "Draw No-Go Zone" tool
2. Click center point of area to protect
3. Drag to set radius of protection zone
4. Name and save the zone

### Home Location Setup

The home location is where your mower returns for charging and storage:

1. **Set Home Location:**
   - Use "Set Home" tool in map toolbar
   - Click on your preferred home location
   - Typically near power source and shelter

2. **Home Location Types:**
   - **Charging Station:** Primary charging location
   - **Storage Location:** Weather protection
   - **Maintenance Area:** Easy access for service

---

## Safety Features

### Comprehensive Safety System

The LawnBerryPi implements multiple layers of safety protection:

**Sensor-Based Safety:**
- **Tilt Detection:** Stops operation on excessive slopes
- **Drop Detection:** Prevents falls from elevated areas  
- **Obstacle Avoidance:** Uses ToF sensors and camera vision
- **Collision Detection:** IMU-based impact detection

**Environmental Safety:**
- **Weather Monitoring:** Automatic rain/snow detection
- **Temperature Limits:** Operation within safe temperature ranges
- **Surface Condition:** Wet grass detection and avoidance

**Geofencing:**
- **Boundary Enforcement:** GPS-based boundary compliance
- **No-Go Zone Respect:** Strict avoidance of protected areas
- **Safe Zone Operations:** Confined to defined areas only

### Emergency Procedures

**Emergency Stop:**
- Large red emergency button always visible
- Immediate halt of all movement and blade operation
- Can be activated from any page in web interface
- Also available via physical button on robot

**Safety Alert Response:**
1. **Immediate Actions:**
   - Stop all movement
   - Turn off cutting blade
   - Activate warning indicators
   - Send notification alerts

2. **Assessment Phase:**
   - Analyze sensor data
   - Determine safety threat level
   - Log incident details

3. **Recovery Actions:**
   - Attempt automatic recovery if safe
   - Return to home if uncertain
   - Require manual intervention for serious issues

### Weather-Based Safety

**Automatic Weather Monitoring:**
- Real-time weather condition assessment  
- Rain detection and immediate stopping
- Wind speed monitoring
- Temperature-based operation limits

**Weather Safety Settings:**
- Maximum wind speed for operation
- Minimum/maximum temperature limits
- Precipitation sensitivity levels
- Forecast-based scheduling

---

## Power Management

### Battery System

**Battery Specifications:**
- 30Ah LiFePO4 battery
- 12V nominal voltage
- Long life cycle (5000+ cycles)
- Built-in protection circuits

**Battery Monitoring:**
- Real-time voltage and current monitoring
- Accurate charge percentage calculation
- Remaining operation time estimates
- Health status tracking

### Solar Charging

**Solar Panel System:**
- 30W monocrystalline panel
- 20A MPPT charge controller
- Weather-resistant construction
- Optimal angle positioning important

**Charging Optimization:**
- Maximum Power Point Tracking (MPPT)
- Temperature compensation
- Overcharge protection
- Charge efficiency monitoring

### Power Management Features

**Battery Conservation:**
- Automatic low-power modes
- Reduced sensor polling when idle
- Efficient sleep states
- Smart service scheduling

**Charging Strategy:**
- Prioritize solar charging during peak sun
- Monitor charging efficiency
- Automatic charging cycle optimization
- Battery health preservation

**Power Alerts:**
- Low battery warnings (configurable thresholds)
- Charging system status notifications
- Power consumption anomaly detection
- Maintenance reminders

---

## Maintenance

### Regular Maintenance Schedule

**Daily Checks (During Active Season):**
- [ ] Visual inspection for damage
- [ ] Check for debris on sensors
- [ ] Verify blade condition
- [ ] Monitor battery level

**Weekly Maintenance:**
- [ ] Clean camera lens
- [ ] Check tire pressure and condition
- [ ] Inspect cutting blade for wear
- [ ] Clean OLED display
- [ ] Verify GPS antenna position

**Monthly Maintenance:**
- [ ] Deep clean all sensors
- [ ] Lubricate moving parts
- [ ] Check all electrical connections
- [ ] Update software if available
- [ ] Calibrate sensors if needed

**Seasonal Maintenance:**
- [ ] Replace cutting blade
- [ ] Full system inspection
- [ ] Battery performance test
- [ ] Solar panel cleaning
- [ ] Weather seal inspection

### Blade Maintenance

**Blade Inspection:**
- Check for chips, cracks, or excessive wear
- Ensure proper balance
- Verify secure mounting

**Blade Replacement:**
1. **Safety First:**
   - Ensure system is powered off
   - Use proper safety equipment
   - Follow lockout/tagout procedures

2. **Removal Process:**
   - Access blade housing
   - Remove securing bolt (reverse thread)
   - Carefully remove worn blade

3. **Installation:**
   - Install new blade with proper orientation
   - Tighten to specified torque
   - Verify balance and clearance
   - Test operation before use

### Sensor Maintenance

**Camera System:**
- Keep lens clean and clear
- Check for proper focus
- Verify mounting stability
- Test image quality regularly

**ToF Sensors:**
- Clean sensor faces regularly
- Check for physical damage
- Verify mounting alignment
- Test distance accuracy

**GPS System:**
- Ensure antenna has clear sky view
- Check for physical damage
- Monitor fix quality and accuracy
- Update antenna position if needed

### Software Maintenance

**Regular Updates:**
- Check for system updates monthly
- Install security patches promptly
- Update weather API keys as needed
- Backup configuration regularly

**System Health Monitoring:**
- Review system logs weekly
- Monitor service status
- Check storage space usage
- Verify network connectivity

---

## Troubleshooting

### Common Issues and Solutions

#### System Won't Start

**Symptoms:** Web interface not accessible, no OLED display

**Possible Causes:**
- Power supply issues
- SD card corruption
- Network connectivity problems

**Solutions:**
1. Check power connections and battery level
2. Verify all cables are securely connected
3. Try power cycling the system
4. Check network connectivity
5. If persistent, check SD card integrity

#### GPS Not Working

**Symptoms:** No location data, "GPS not available" messages

**Possible Causes:**
- Obstructed antenna
- Poor satellite visibility
- Hardware connection issues

**Solutions:**
1. Ensure GPS antenna has clear sky view
2. Check for physical obstructions
3. Verify USB connection (/dev/ttyACM0)
4. Allow 5-10 minutes for initial GPS lock
5. Check antenna cable connections

#### Obstacle Detection Issues

**Symptoms:** Mower hitting obstacles, false obstacle detection

**Possible Causes:**
- Dirty sensors
- Misaligned sensors
- Sensitivity settings

**Solutions:**
1. Clean ToF sensor faces thoroughly
2. Check sensor mounting and alignment
3. Adjust sensitivity settings in configuration
4. Verify sensor power connections
5. Test sensors individually

#### Battery Not Charging

**Symptoms:** Battery level decreasing despite sunlight

**Possible Causes:**
- Solar panel issues
- Charge controller problems
- Battery degradation

**Solutions:**
1. Check solar panel for shading or dirt
2. Verify charge controller connections
3. Monitor charging current and voltage
4. Check battery health status
5. Inspect all power connections

#### Web Interface Slow/Unresponsive

**Symptoms:** Pages load slowly, timeouts, connection errors

**Possible Causes:**
- High system load
- Network issues
- Service problems

**Solutions:**
1. Check system resource usage
2. Restart web services
3. Verify network connectivity
4. Clear browser cache
5. Check for software updates

### Diagnostic Tools

**System Health Check:**
- Access via Settings > System > Diagnostics
- Comprehensive system status report
- Service health monitoring
- Performance metrics

**Sensor Test Mode:**
- Individual sensor testing
- Real-time sensor data display
- Calibration verification
- Connection status check

**Log Analysis:**
- Access system logs via web interface
- Filter by service or time period
- Export logs for detailed analysis
- Error pattern identification

### Getting Help

**Documentation Resources:**
- Complete user manual (this document)
- API reference documentation
- Hardware specifications
- Safety guidelines

**Community Support:**
- User forums and discussion groups
- Knowledge base articles
- Video tutorials
- FAQ database

**Technical Support:**
- System diagnostic reports
- Remote assistance capability
- Hardware replacement procedures
- Software update guidance

---

## Advanced Configuration

### Expert User Settings

**Performance Tuning:**
- CPU and memory optimization
- Service priority adjustment
- Network bandwidth allocation
- Storage management

**Custom Patterns:**
- Pattern algorithm parameters
- Coverage optimization settings
- Efficiency vs. thoroughness balance
- Custom pattern creation

**Safety System Customization:**
- Sensor fusion parameters
- Threshold adjustments
- Response timing configuration
- Custom safety rules

### Developer Options

**API Configuration:**
- Custom endpoint development
- WebSocket message customization
- Data export formats
- Integration capabilities

**Plugin System:**
- Third-party plugin installation
- Custom service development
- Hardware abstraction extensions
- Custom UI components

### System Administration

**User Management:**
- Multi-user access control
- Role-based permissions
- Authentication configuration
- Audit logging

**Backup and Recovery:**
- Automated backup scheduling
- Configuration export/import
- System restore procedures
- Data migration tools

**Monitoring and Alerting:**
- Custom alert rules
- Performance monitoring
- Capacity planning
- Health check scheduling

---

## Appendices

### Appendix A: Technical Specifications

**Raspberry Pi 4B Configuration:**
- CPU: Quad-core ARM Cortex-A72 @ 1.5GHz
- RAM: 16GB LPDDR4
- Storage: MicroSD card (minimum 32GB, recommend 64GB+)
- Operating System: Raspberry Pi OS 64-bit (Bookworm)

**Power System Specifications:**
- Battery: 30Ah LiFePO4, 12V nominal
- Solar Panel: 30W monocrystalline
- Charge Controller: 20A MPPT
- Power Consumption: 45-60W typical operation

**Navigation Accuracy:**
- RTK GPS: <10cm positioning accuracy
- ToF Sensors: 30-2000mm range, ±3% accuracy
- IMU: 0.1° heading accuracy

### Appendix B: Safety Certifications

The LawnBerryPi system complies with relevant safety standards:
- IP54 weather resistance rating
- Low voltage electrical safety standards
- Electromagnetic compatibility requirements
- Blade safety specifications

### Appendix C: Warranty and Support

**Hardware Warranty:**
- 2-year warranty on custom electronics
- 1-year warranty on commercial components
- 6-month warranty on wear items (blades, tires)

**Software Support:**
- Free software updates for 3 years
- Security patches and bug fixes
- Community support forum access
- Documentation updates

---

**Document Version:** 1.0  
**Last Updated:** December 2024  
**Next Review:** March 2025

For the most current version of this manual and additional resources, visit the official LawnBerryPi documentation website.
