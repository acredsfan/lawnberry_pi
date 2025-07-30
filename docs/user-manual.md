# LawnBerryPi User Manual

Welcome to your LawnBerryPi autonomous lawn mower! This comprehensive guide will teach you everything you need to know to operate your mower safely and effectively.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Understanding the Dashboard](#understanding-the-dashboard)
3. [Setting Up Your Yard](#setting-up-your-yard)
4. [Mowing Operations](#mowing-operations)
5. [Scheduling](#scheduling)
6. [Monitoring & Maintenance](#monitoring--maintenance)
7. [Advanced Features](#advanced-features)
8. [Safety Guidelines](#safety-guidelines)

## Getting Started

### Accessing Your LawnBerryPi

1. **Connect to the same WiFi network** as your LawnBerryPi
2. **Open a web browser** on any device (phone, tablet, computer)
3. **Navigate to your LawnBerryPi's address**: `http://[your-lawnberry-ip]:3000`
   - Find IP address: Check your router's admin panel or use a network scanner app
   - Example: `http://192.168.1.100:3000`

### First Login

When you first access your LawnBerryPi, you'll see the main dashboard. No login is required - the system is designed for easy access on your home network.

### System Status Indicators

At the top of every page, you'll see status indicators:

- 🟢 **Green**: System operating normally
- 🟡 **Yellow**: Warning or attention needed
- 🔴 **Red**: Error or safety issue
- ⚫ **Gray**: Component offline or disabled

## Understanding the Dashboard

### Main Dashboard Layout

The dashboard is your command center, showing real-time information about your LawnBerryPi:

#### 🎛️ System Status Panel (Top Left)
- **Mower Status**: Currently mowing, returning home, charging, or idle
- **Battery Level**: Current charge percentage and estimated runtime
- **GPS Status**: Satellite lock status and current location accuracy
- **Weather**: Current conditions and mowing suitability

#### 🗺️ Live Map View (Center)
- **Real-time position**: Blue dot shows current mower location
- **Yard boundaries**: Green lines show your defined mowing area
- **No-go zones**: Red areas that the mower will avoid  
- **Mowing progress**: Darker green shows areas already mowed today
- **Home position**: House icon shows charging/storage location

#### 📊 Sensor Data (Right Panel)
- **Camera feed**: Live view from mower's camera with object detection
- **Obstacle detection**: Distance readings from front sensors
- **Environmental data**: Temperature, humidity, air pressure
- **Power monitoring**: Battery voltage, current draw, solar charging

#### 🎮 Quick Controls (Bottom)
- **Start/Stop**: Begin or end mowing operations
- **Return Home**: Send mower back to charging station
- **Emergency Stop**: Immediately stop all operations
- **Manual Control**: Direct mower movement (for positioning)

### Navigation Menu

The left sidebar provides access to all LawnBerryPi features:

- 🏠 **Dashboard**: Main status and control screen
- 🗺️ **Mapping**: Set up yard boundaries and no-go zones
- 📅 **Scheduler**: Create and manage mowing schedules
- 📊 **History**: View mowing statistics and logs
- 🔧 **Settings**: Configure system preferences
- 🛠️ **Maintenance**: Hardware status and diagnostics
- ❓ **Help**: Quick reference and support

## Setting Up Your Yard

### Step 1: Define Your Mowing Area

Before your first mow, you need to define where the mower should operate:

1. **Go to Mapping page** (🗺️ icon in sidebar)
2. **Ensure GPS lock**: Wait for "GPS: LOCKED" status (may take 2-5 minutes outdoors)
3. **Walk the boundary**:
   - Click "Start Boundary Definition"
   - Walk slowly around the perimeter of your lawn
   - Stay 3-4 feet inside any obstacles (fences, flower beds, etc.)
   - The map will show your path as a green line
   - Click "Complete Boundary" when you return to start

**💡 Tips for Boundary Setting**:
- Walk at normal pace (2-3 mph) for best GPS accuracy
- Stay consistent distance from obstacles
- Include buffer space for safety
- You can edit boundaries later if needed

### Step 2: Set No-Go Zones

Protect sensitive areas by creating no-go zones:

1. **In Mapping page**: Click "Add No-Go Zone"
2. **Draw on map**: Click points to create a polygon around areas to avoid
   - Flower beds and gardens
   - Play equipment or outdoor furniture  
   - Sprinkler heads
   - Slopes steeper than 20 degrees
   - Areas with loose objects
3. **Save zones**: Click "Save No-Go Zone" for each area

### Step 3: Set Home Position

Define where your mower should return for charging:

1. **Position mower** at desired home location (near power source)
2. **In Mapping page**: Click "Set Home Position"
3. **Verify location**: Ensure home marker appears at correct spot on map

## Mowing Operations

### Starting Your First Mow

1. **Pre-mow checklist**:
   - ✅ Battery charged above 20%
   - ✅ Weather suitable (no rain forecast)
   - ✅ Yard clear of toys, tools, and debris
   - ✅ Blade sharp and properly installed
   - ✅ GPS has satellite lock

2. **Select mowing pattern**:
   - **Parallel**: Straight lines across the yard (most efficient)
   - **Checkerboard**: Perpendicular passes (best cut quality)
   - **Spiral**: Outside-in spiral pattern (good for irregular shapes)
   - **Random**: Randomized pattern (natural appearance)

3. **Set mowing parameters**:
   - **Speed**: 0.5-2.0 m/s (start with 1.0 m/s)
   - **Cut height**: Adjust blade height for grass type
   - **Overlap**: 10-20% overlap between passes

4. **Start mowing**: Click the large "START MOWING" button

### Monitoring Active Mowing

While mowing, the dashboard shows:

- **Live position**: Blue dot moving across the map
- **Progress**: Percentage of area completed
- **Estimated time**: Time remaining to complete
- **Current activity**: "Mowing", "Turning", "Avoiding obstacle"
- **Statistics**: Area covered, runtime, battery usage

### Automatic Features

Your LawnBerryPi automatically handles:

- **Obstacle avoidance**: Uses sensors to navigate around objects
- **Weather monitoring**: Pauses mowing if rain detected
- **Battery management**: Returns home when charge gets low
- **Pattern optimization**: Learns efficient routes over time
- **Safety monitoring**: Stops if lifted or tilted beyond safe angles

### Manual Control

For positioning or testing, you can manually control the mower:

1. **Click "Manual Control"** in the dashboard
2. **Use direction buttons** to move the mower:
   - ⬆️ Forward
   - ⬇️ Reverse  
   - ⬅️ Turn left
   - ➡️ Turn right
   - ⏹️ Stop
3. **Click "Exit Manual Mode"** to return to automatic operation

**⚠️ Safety Note**: Manual control should only be used for positioning. Never manually operate the mower with blades spinning.

## Scheduling

### Creating Mowing Schedules

Automate your lawn care with intelligent scheduling:

1. **Go to Scheduler page** (📅 icon)
2. **Click "Create New Schedule"**
3. **Set schedule parameters**:

   **Days of Week**:
   - Select which days to mow
   - Most lawns benefit from 3-4 mows per week

   **Time Windows**:
   - Start time: When mowing can begin
   - End time: When mowing must stop
   - Consider noise ordinances and family activities

   **Weather Conditions**:
   - ✅ Only mow when dry (recommended)
   - ✅ Skip if rain forecast within 2 hours
   - ✅ Avoid extreme temperatures (below 40°F or above 90°F)

   **Pattern Rotation**:
   - Automatically vary patterns to prevent ruts
   - Promotes healthier grass growth

4. **Save schedule**: Click "Save Schedule"

### Example Schedules

**Typical Residential (3x/week)**:
- Days: Monday, Wednesday, Friday
- Time: 9:00 AM - 5:00 PM  
- Pattern: Rotate between parallel and checkerboard
- Weather: Skip if rain within 2 hours

**Large Property (Daily)**:
- Days: Monday-Saturday
- Time: 7:00 AM - 7:00 PM
- Pattern: Parallel (most efficient)
- Weather: Skip if rain within 1 hour

**Quiet Neighborhood (Limited hours)**:
- Days: Tuesday, Thursday, Saturday
- Time: 10:00 AM - 3:00 PM
- Pattern: Random (quieter)
- Weather: Skip if rain within 3 hours

### Schedule Management

- **Edit schedules**: Click pencil icon next to any schedule
- **Disable temporarily**: Use toggle switch to pause without deleting
- **Multiple schedules**: Create different schedules for different seasons
- **Manual override**: Start immediate mowing even if not scheduled

## Monitoring & Maintenance

### Daily Monitoring

Check these daily during mowing season:

1. **Battery status**: Ensure charging properly overnight
2. **Weather forecast**: Verify schedule appropriateness  
3. **Mowing progress**: Check that scheduled mows completed
4. **Camera view**: Look for new obstacles or issues

### Weekly Checks

Perform these weekly maintenance tasks:

1. **Clean camera lens**: Wipe with soft, dry cloth
2. **Check blade sharpness**: Replace if dull or damaged
3. **Inspect wheels**: Remove grass buildup and debris
4. **Review mowing statistics**: Adjust schedules based on performance

### Monthly Maintenance

More thorough monthly checks:

1. **Battery performance**: Check charging time and runtime
2. **Sensor calibration**: Verify GPS and compass accuracy
3. **Software updates**: Install any available updates
4. **Hardware inspection**: Look for loose connections or wear

### Understanding Statistics

The History page provides valuable insights:

**Mowing Metrics**:
- Total area mowed per session
- Average speed and efficiency
- Battery usage per square foot
- Pattern completion rates

**System Health**:
- Sensor reading accuracy
- GPS satellite count and accuracy
- Component operating temperatures
- Error frequency and types

**Trends and Optimization**:
- Best performing mowing patterns
- Optimal weather conditions
- Battery degradation over time
- Schedule effectiveness

## Advanced Features

### AI Training Mode

Help your LawnBerryPi learn your specific yard:

1. **Enable Training Mode** in Settings → Advanced
2. **Collect training data**: Mower captures images while operating
3. **Label objects**: Use web interface to identify obstacles
   - Mark sprinkler heads, decorations, pet toys
   - Identify grass types and growth patterns
   - Tag seasonal obstacles (fallen leaves, snow)
4. **Deploy custom model**: System learns your yard's unique features

### Fleet Management

If you have multiple LawnBerryPi units:

1. **Enable Fleet Mode** in Settings → Fleet
2. **Coordinate schedules**: Prevent conflicts between units
3. **Share maps**: Use boundary definitions across units
4. **Centralized monitoring**: View all units from single dashboard

### Weather Integration

Advanced weather features:

- **Hyperlocal forecasts**: Uses multiple weather sources
- **Soil moisture estimation**: Factors rainfall and temperature
- **Growing degree days**: Optimizes mowing frequency for grass growth
- **Seasonal adjustments**: Automatically adapts to changing conditions

### Custom Notifications

Configure alerts for your preferences:

1. **Go to Settings → Notifications**
2. **Choose notification methods**:
   - Web browser notifications
   - Email alerts
   - Mobile push notifications (if PWA installed)
3. **Set alert conditions**:
   - Mowing completion
   - Errors or safety stops
   - Low battery warnings
   - Weather delays
   - Maintenance reminders

## Safety Guidelines

### Before Every Use

⚠️ **CRITICAL SAFETY CHECKS**:

1. **Clear the area**: Remove toys, tools, sticks, and debris
2. **Check blade condition**: Replace if damaged or excessively dull
3. **Verify boundaries**: Ensure no new obstacles inside mowing area
4. **Weather check**: Do not operate in wet conditions
5. **People and pets**: Ensure no one will be in mowing area

### During Operation

- **Never approach** the mower while blades are spinning
- **Use emergency stop** if anyone enters the mowing area
- **Monitor remotely**: Check camera feed and status regularly
- **Stay alert**: Be ready to intervene if unusual behavior occurs

### Emergency Procedures

**If Something Goes Wrong**:

1. **Press Emergency Stop** immediately (big red button in dashboard)
2. **Physically approach** only after confirming blades have stopped
3. **Lift and inspect** the mower to identify the issue
4. **Clear any obstructions** before resuming operation
5. **Test safety systems** before returning to automatic mode

**Emergency Stop Methods**:
- Dashboard emergency button (fastest)
- Lift the mower (automatic safety stop)
- Tilt beyond 30 degrees (automatic safety stop)
- Physical emergency button on mower (if equipped)

### Child and Pet Safety

- **Supervise children** around the mower at all times
- **Keep pets indoors** during mowing operations
- **Use no-go zones** around play areas
- **Install safety barriers** if needed for high-traffic areas
- **Consider scheduling** mowing when family is away

### Weather Safety

**Do Not Operate In**:
- Rain or wet conditions
- High winds (over 25 mph)
- Temperatures below 35°F or above 95°F
- Lightning or thunderstorm conditions
- Fog with visibility under 50 feet

### Maintenance Safety

- **Disconnect power** before any maintenance
- **Use proper tools** for blade changes and adjustments
- **Wear protective equipment**: Safety glasses and gloves
- **Follow lockout procedures** when working on electrical systems

## Troubleshooting Quick Reference

### Common Issues and Solutions

**Mower won't start**:
- Check battery charge level
- Verify GPS has satellite lock
- Ensure emergency stop is not activated
- Check weather conditions

**Poor cutting quality**:
- Sharpen or replace blade
- Adjust cutting height
- Slow down mowing speed
- Check for blade damage

**Navigation problems**:
- Recalibrate GPS and compass
- Clean sensor lenses
- Check for interference sources
- Verify boundary definitions

**Battery issues**:
- Check charging connections
- Clean solar panel surface
- Monitor charging controller status
- Consider battery replacement if old

For detailed troubleshooting, see our [Troubleshooting Guide](troubleshooting-guide.md).

## Getting Help

- **Built-in Help**: Click ❓ icon in any page for context-specific help
- **Documentation**: Complete guides available in `/docs` folder
- **Diagnostics**: Run hardware tests from Maintenance page
- **Community**: Share experiences with other LawnBerryPi users

---

**Enjoy your autonomous lawn care!** Your LawnBerryPi is designed to learn and improve over time. The more you use it, the better it becomes at maintaining your specific lawn.

*User Manual - Part of LawnBerryPi Documentation v1.0*
