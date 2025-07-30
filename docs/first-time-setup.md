# LawnBerryPi First-Time Setup Guide

Welcome to your first-time setup! This guide walks you through configuring your LawnBerryPi for your specific yard and preferences. Complete these steps after successful installation.

## Prerequisites

Before starting first-time setup:
- ✅ LawnBerryPi software installed and running
- ✅ All hardware connected and tested
- ✅ Web interface accessible at `http://[your-pi-ip]:3000`
- ✅ GPS has satellite lock (may take 5-10 minutes outdoors)
- ✅ API keys configured in environment file

## Step 1: Initial System Configuration

### Access the Setup Wizard

1. **Open web browser** and navigate to your LawnBerryPi
2. **First visit** should automatically show "First-Time Setup Wizard"
3. **If not available**: Go to Settings → System → Run Setup Wizard

### Basic System Settings

**System Information**:
- **Mower Name**: Give your LawnBerryPi a memorable name
- **Location**: Verify your address/coordinates for weather data
- **Timezone**: Set correct timezone for scheduling
- **Units**: Choose metric or imperial measurements

**Example Configuration**:
```
Mower Name: "BackyardBot"
Location: "123 Main St, Anytown, USA"
Timezone: "America/New_York"
Units: Imperial (feet, Fahrenheit)
```

### User Preferences

**Interface Settings**:
- **Theme**: Light, dark, or auto (follows device preference)
- **Dashboard Layout**: Compact or detailed view
- **Update Frequency**: How often to refresh data (default: 5 seconds)
- **Sound Alerts**: Enable/disable audio notifications

**Safety Preferences**:
- **Confirmation Required**: Require confirmation for start/stop commands
- **Emergency Contact**: Phone number for emergency situations
- **Operating Hours**: Default hours when mowing is allowed

## Step 2: Hardware Calibration

### GPS and Navigation Setup

**GPS Accuracy Test**:
1. **Position mower outdoors** with clear sky view
2. **Wait for GPS lock** (GPS status should show "LOCKED")
3. **Record baseline position**:
   - Go to Settings → Hardware → GPS Status
   - Note current coordinates and accuracy
   - Should show accuracy better than 3 meters

**Compass Calibration**:
1. **Start calibration**: Settings → Hardware → IMU Calibration
2. **Follow on-screen instructions**:
   - Slowly rotate mower through complete 360° turn
   - Perform figure-8 motions in horizontal plane
   - Tilt mower gently through various angles
3. **Verify calibration**: Compass should show correct magnetic heading

### Sensor Calibration

**Obstacle Detection Setup**:
1. **Go to**: Settings → Hardware → Obstacle Detection
2. **Test sensors**:
   - Place object 2 feet in front of mower
   - Verify distance reading is approximately correct
   - Move object to 1 foot, 3 feet - readings should update
3. **Set sensitivity**:
   - **High sensitivity**: Stops for small objects (recommended)
   - **Medium sensitivity**: Ignores very small objects
   - **Low sensitivity**: Only stops for large obstacles

**Camera Setup**:
1. **Verify camera feed**: Should show clear image from mower's perspective
2. **Adjust settings if needed**:
   - **Brightness**: Adjust for lighting conditions
   - **Contrast**: Enhance object visibility
   - **Focus**: Should be automatic, but can be manual if needed

### Battery System Configuration

**Power Monitoring Setup**:
1. **Verify readings**: Settings → Hardware → Power Monitor
2. **Set thresholds**:
   - **Low battery warning**: 30% (adjust based on your needs)
   - **Return home threshold**: 20% (ensures safe return)
   - **Emergency reserve**: 10% (for emergency operations only)

**Charging Configuration**:
- **Solar panel efficiency**: Monitor charging rate in full sun
- **Charge controller settings**: Verify appropriate for your battery type
- **Charging schedule**: Set preferred charging times if needed

## Step 3: Yard Mapping and Boundaries

### Create Your Mowing Boundary

**⚠️ Important**: This is the most critical setup step. Take your time and be precise.

**Preparation**:
1. **Plan your route**: Walk around your property and plan the boundary path
2. **Stay inside obstacles**: Maintain 3-4 feet clearance from:
   - Fences and walls
   - Flower beds and gardens
   - Trees and large shrubs
   - Permanent outdoor furniture
   - Driveways and walkways
3. **Consider safety zones**: Extra clearance around:
   - Play equipment
   - Pet areas
   - Frequently used paths

**Boundary Definition Process**:
1. **Go to Mapping page** (🗺️ icon in sidebar)
2. **Start boundary definition**:
   - Click "Start Boundary Definition"
   - Choose starting point (usually near home position)
3. **Walk the boundary**:
   - Walk slowly (2-3 mph) around perimeter
   - Stay consistent distance from obstacles
   - GPS will record your path as green line on map
   - Take your time - accuracy is important
4. **Complete boundary**:
   - Return to starting point
   - Click "Complete Boundary" when path connects
   - System will show total area and boundary length

**Boundary Tips**:
- **Walk the same path twice** for better accuracy
- **Avoid walking during GPS poor conditions** (cloudy, near buildings)
- **Include slopes less than 20 degrees** only
- **Create wide turns** - avoid sharp corners that are hard to mow
- **Consider seasonal changes** - leave room for plant growth

### Set Home Position

**Choose Home Location**:
- **Near power source**: Should be close to charging setup
- **Protected area**: Covered or sheltered location preferred
- **Easy access**: For maintenance and manual operation
- **Level ground**: Avoid slopes for charging stability

**Set Home Position**:
1. **Position mower** at desired home location
2. **Verify GPS accuracy** (should be < 2 meters)
3. **Click "Set Home Position"** in mapping interface
4. **Confirm location**: Home marker should appear at correct spot

### Define No-Go Zones

**Identify Areas to Avoid**:
- Flower beds and vegetable gardens
- Sprinkler heads and irrigation equipment
- Decorative objects and lawn art
- Play equipment and outdoor furniture
- Steep slopes (>20 degrees)
- Wet or soft areas
- Property boundaries requiring precision

**Create No-Go Zones**:
1. **In Mapping page**: Click "Add No-Go Zone"
2. **Draw zone boundary**:
   - Click points around area to avoid
   - Include adequate buffer space
   - Close polygon by clicking first point again
3. **Name and save zone**: Give descriptive name for easy identification
4. **Test boundary**: Use simulation mode to verify mower avoids area

## Step 4: Mowing Configuration

### Choose Initial Mowing Pattern

**Pattern Selection Guidelines**:

**For Large, Open Areas**:
- **Primary**: Parallel pattern (most efficient)
- **Secondary**: Checkerboard for best cut quality
- **Avoid**: Random pattern (inefficient for large areas)

**For Complex or Irregular Yards**:
- **Primary**: Spiral pattern (handles irregular shapes well)
- **Secondary**: Random pattern (natural appearance)
- **Consider**: Breaking into zones with different patterns

**For Mixed Terrain**:
- **Primary**: Checkerboard (thorough coverage)
- **Secondary**: Parallel with high overlap
- **Consider**: Manual pattern selection for problem areas

### Set Mowing Parameters

**Speed Settings**:
- **Start with**: 1.0 m/s (moderate speed)
- **Increase to**: 1.5 m/s if cut quality is good
- **Decrease to**: 0.8 m/s for thick grass or uneven terrain
- **Maximum**: 2.0 m/s only for smooth, open areas

**Cutting Height**:
- **Spring**: Higher setting (3-4 inches) for initial cuts
- **Summer**: Medium setting (2.5-3 inches) for regular maintenance
- **Fall**: Gradually lower for final cuts
- **Rule**: Never cut more than 1/3 of grass height in single pass

**Overlap Settings**:
- **Standard**: 15% overlap between passes
- **High quality**: 20% overlap for thick or uneven grass
- **Efficient**: 10% overlap for regular maintenance
- **Problem areas**: Up to 25% overlap if needed

### Safety Configuration

**Obstacle Detection**:
- **Sensitivity**: Start with "High" setting
- **Stopping distance**: 0.5 meters from obstacles
- **Override capability**: Disable for advanced users only

**Weather Monitoring**:
- **Rain detection**: Enable automatic rain stopping
- **Wind limits**: Stop operation in winds >20 mph
- **Temperature limits**: 40-85°F operating range
- **Forecast monitoring**: Check weather 2 hours ahead

**Emergency Systems**:
- **Tilt detection**: Enable automatic stop if lifted/tilted
- **Emergency contact**: Set phone number for alerts
- **Automatic return**: Enable low-battery return home
- **Communication loss**: Return home if lose connection >5 minutes

## Step 5: Create Your First Schedule

### Basic Schedule Setup

**Determine Mowing Frequency**:
- **Grass growth rate**: Varies by season and grass type
- **Typical residential**: 3-4 times per week during growing season
- **Large properties**: Daily mowing may be needed
- **Low-maintenance**: 2 times per week minimum

**Choose Mowing Days**:
- **Recommended**: Monday, Wednesday, Friday (every other day)
- **Daily option**: Monday-Saturday (rest on Sunday)
- **Weekend option**: Saturday and Sunday only
- **Custom**: Based on your schedule and grass growth

**Set Time Windows**:
- **Start time**: When mowing can begin (consider noise ordinances)
- **End time**: When mowing must stop (before evening activities)
- **Typical window**: 9:00 AM - 5:00 PM
- **Quiet neighborhood**: 10:00 AM - 3:00 PM

### Create Your Schedule

1. **Go to Scheduler page** (📅 icon)
2. **Click "Create New Schedule"**
3. **Configure schedule**:
   - **Name**: "Regular Maintenance" (or your preference)
   - **Days**: Select your chosen days
   - **Start time**: Your preferred start time
   - **End time**: Your preferred end time
   - **Pattern**: Your chosen mowing pattern
   - **Weather conditions**: Enable weather monitoring
4. **Save schedule**

**Example Schedule**:
```
Name: "Spring Maintenance"
Days: Monday, Wednesday, Friday
Time: 9:00 AM - 4:00 PM
Pattern: Parallel (rotate to checkerboard weekly)
Weather: Skip if rain within 2 hours
Speed: 1.0 m/s
```

### Test Your Schedule

**Schedule Verification**:
1. **Enable schedule**: Turn on your newly created schedule
2. **Check next run**: Verify next scheduled mowing time is correct
3. **Manual test**: Run a short manual mowing session first
4. **Monitor first scheduled run**: Stay available to intervene if needed

## Step 6: First Test Mow

### Pre-Test Preparation

**Safety Setup**:
- [ ] Complete area inspection and clearing
- [ ] All family members and pets secured
- [ ] Emergency procedures reviewed
- [ ] Web interface accessible for monitoring
- [ ] First aid kit accessible

**Start Small**:
- **Limited area**: Choose small, safe section for first test
- **Short duration**: 15-30 minutes maximum
- **Stay nearby**: Monitor closely during first run
- **Good conditions**: Optimal weather and lighting

### Conduct Test Mow

1. **Final safety check**: Complete daily checklist
2. **Start mowing**: Use web interface to begin operation
3. **Monitor closely**:
   - Watch live camera feed
   - Check position tracking on map
   - Verify obstacle detection working
   - Listen for unusual sounds
4. **Test emergency stop**: Practice stopping and restarting
5. **Evaluate performance**:
   - Cutting quality
   - Navigation accuracy
   - Battery usage
   - Any issues or concerns

### Post-Test Evaluation

**Check Results**:
- **Cut quality**: Even height, clean cuts, no missed spots
- **Navigation**: Followed boundaries accurately, avoided obstacles
- **System performance**: No errors, warnings, or unexpected behavior
- **Battery usage**: Reasonable consumption for area covered

**Make Adjustments**:
- **Speed**: Increase/decrease based on cut quality and efficiency
- **Pattern**: Try different pattern if current one isn't optimal
- **Boundaries**: Adjust if mower went too close to obstacles
- **Sensitivity**: Adjust obstacle detection if too sensitive/insensitive

## Step 7: Monitoring and Optimization

### Set Up Monitoring Routine

**Daily Monitoring**:
- Check dashboard status each morning
- Verify weather conditions suitable
- Review previous day's mowing results
- Clear any debris from mowing area

**Weekly Review**:
- Analyze mowing statistics and efficiency
- Check battery performance trends
- Review any errors or warnings
- Adjust schedule based on grass growth

**Monthly Optimization**:
- Fine-tune boundaries based on experience
- Adjust patterns for seasonal conditions
- Update no-go zones for landscape changes
- Review and update safety procedures

### Performance Monitoring

**Key Metrics to Track**:
- **Coverage efficiency**: Percentage of area mowed per session
- **Battery usage**: Runtime per charge and charging time
- **Cut quality**: Visual assessment of mowing results
- **Error frequency**: Number and types of errors encountered
- **Weather delays**: How often weather stops operation

**Optimization Opportunities**:
- **Pattern rotation**: Change patterns weekly to prevent ruts
- **Speed adjustment**: Find optimal speed for your grass type
- **Schedule refinement**: Adjust frequency based on growth rate
- **Boundary improvements**: Fine-tune based on operation experience

## Troubleshooting First-Time Setup

### Common Setup Issues

**GPS Won't Lock**:
- Ensure mower is outdoors with clear sky view
- Wait up to 15 minutes for initial satellite acquisition
- Check for GPS interference from buildings or power lines
- Verify GPS antenna connection

**Boundary Definition Problems**:
- Walk slower (2-3 mph) for better GPS accuracy
- Avoid walking during poor GPS conditions
- Include adequate buffer space from obstacles
- Try walking boundary multiple times for better accuracy

**Camera or Sensor Issues**:
- Clean all sensor lenses and camera
- Check connections and cables
- Verify proper mounting and orientation
- Test sensors individually in hardware diagnostics

**Web Interface Problems**:
- Verify correct IP address and port (3000)
- Check network connection and firewall settings
- Try different browser or clear cache
- Restart web services if needed

### Getting Help During Setup

**Built-in Help**:
- Click "?" icon on any page for context-specific help
- Use "Help" section in sidebar for detailed guides
- Check "Hardware Status" page for diagnostic information

**Documentation Resources**:
- [User Manual](user-manual.md) for detailed operation instructions
- [Troubleshooting Guide](troubleshooting-guide.md) for problem solving
- [Safety Guide](safety-guide.md) for important safety information

## Setup Completion Checklist

When you've completed first-time setup:

### System Configuration
- [ ] Basic system settings configured
- [ ] User preferences set
- [ ] API keys working correctly
- [ ] All hardware calibrated

### Mapping and Boundaries
- [ ] Mowing boundary defined accurately
- [ ] Home position set appropriately
- [ ] No-go zones created for all hazards
- [ ] Boundaries tested with simulation

### Mowing Configuration
- [ ] Appropriate mowing pattern selected
- [ ] Speed and cutting parameters set
- [ ] Safety systems configured and tested
- [ ] Weather monitoring enabled

### Scheduling
- [ ] Initial schedule created
- [ ] Schedule tested and verified
- [ ] Monitoring routine established
- [ ] Emergency procedures practiced

### Testing and Validation
- [ ] Test mow completed successfully
- [ ] Performance evaluated and optimized
- [ ] Any issues identified and resolved
- [ ] Family members trained on basic operation

## Next Steps

After completing first-time setup:

1. **Start Regular Operation**: Begin using your schedule with close monitoring
2. **Learn and Adjust**: Fine-tune settings based on experience
3. **Maintain Regularly**: Follow maintenance schedule to keep system optimal
4. **Stay Updated**: Keep software current and review documentation updates

**Congratulations!** Your LawnBerryPi is now configured and ready for autonomous lawn care. Take time to observe its operation and make adjustments as needed for optimal performance.

---

*First-Time Setup Guide - Part of LawnBerryPi Documentation v1.0*
