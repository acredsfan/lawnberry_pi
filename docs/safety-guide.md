# LawnBerryPi Safety Guide

**⚠️ CRITICAL: Read this entire safety guide before operating your LawnBerryPi. Failure to follow these safety guidelines could result in serious injury or death.**

The LawnBerryPi is a powerful autonomous machine with sharp rotating blades. It must be operated with extreme caution and proper safety measures at all times.

## Emergency Contact Information

**In case of serious injury**: Call emergency services immediately (911 in US)

**Emergency Shutdown Methods** (in order of speed):
1. **Web Interface Emergency Stop** - Fastest (if you have device access)
2. **Physical Emergency Button** - On mower unit (if equipped)
3. **Lift the Mower** - Automatic safety stop when tilted >30°
4. **Power Disconnect** - Pull main power disconnect

## Before First Use - Mandatory Safety Setup

### 1. Read All Documentation
- [ ] Complete this safety guide
- [ ] Read user manual sections on operation
- [ ] Understand emergency procedures
- [ ] Review troubleshooting guide

### 2. Inspect Hardware
- [ ] Verify all safety systems are functional
- [ ] Test emergency stop mechanisms
- [ ] Check blade installation and condition
- [ ] Ensure all guards and covers are secure

### 3. Test Safety Systems
- [ ] Emergency stop button (web interface)
- [ ] Tilt safety stop (lift mower slightly)
- [ ] Obstacle detection (place object in front)
- [ ] Weather safety (verify rain detection)

### 4. Establish Safety Zones
- [ ] Create no-go zones around hazards
- [ ] Install physical barriers if needed
- [ ] Post warning signs in mowing area
- [ ] Inform neighbors of operation schedule

## Personal Safety Requirements

### Before Every Use

**MANDATORY SAFETY CHECKLIST**:
- [ ] **Area Clear**: Remove all people, pets, toys, tools, and debris
- [ ] **Weather Check**: Dry conditions only - no rain forecast within 2 hours
- [ ] **Blade Inspection**: Sharp, secure, undamaged blade properly installed
- [ ] **Boundary Verification**: No new obstacles within mowing boundaries
- [ ] **Safety Systems Test**: Emergency stop and tilt detection functional
- [ ] **Escape Plan**: Know how to quickly shut down system remotely

### Personal Protective Equipment (PPE)

When performing maintenance or manual operation:
- **Safety glasses**: Protect eyes from debris
- **Heavy gloves**: Cut-resistant when handling blade
- **Closed-toe shoes**: Steel-toed preferred when working on mower
- **Long pants**: Protect legs from blade and debris

### Prohibited Actions

**NEVER do the following**:
- ❌ Approach mower while blades are spinning
- ❌ Allow children or pets in mowing area during operation
- ❌ Override safety systems or sensors
- ❌ Operate in wet, icy, or unstable ground conditions
- ❌ Leave mower unattended without remote monitoring capability
- ❌ Manually move mower with blades engaged
- ❌ Disable emergency stop systems
- ❌ Operate with damaged or missing safety guards

## Child and Pet Safety

### Absolute Requirements

**Children (Under 18)**:
- Must NEVER be in mowing area during operation
- Should be supervised when mower is present but not operating
- Must be taught to recognize mower and stay away
- Emergency stop procedures must be explained to older children

**Pets**:
- Must be kept indoors or in secure area during mowing
- Pet areas should be designated as no-go zones
- Consider pet detection systems for additional safety
- Train pets to avoid mower area

### Physical Safety Barriers

Install barriers around:
- Play areas and swing sets
- Pet runs and outdoor pet areas
- Frequently used walkways
- Outdoor dining/entertainment areas

Consider:
- Physical fencing or barriers
- Motion sensors with automatic stop
- Designated safe zones clearly marked
- Scheduled mowing when family is away

## Environmental Safety Conditions

### Safe Operating Conditions

**Weather Requirements**:
- ✅ Dry grass and ground conditions
- ✅ Temperature between 40°F - 85°F (4°C - 29°C)
- ✅ Wind speed under 20 mph (32 km/h)
- ✅ No precipitation for 4+ hours
- ✅ Good visibility (no fog)

**Ground Conditions**:
- ✅ Firm, stable ground surface
- ✅ Slopes less than 20 degrees (36% grade)
- ✅ No loose objects or debris
- ✅ Adequate drainage (no standing water)

### Unsafe Operating Conditions

**STOP OPERATION immediately if**:
- 🚫 Rain begins or is forecast within 2 hours
- 🚫 Ground becomes soft or muddy
- 🚫 High winds develop (>20 mph)
- 🚫 Visibility reduces due to fog or dust
- 🚫 Temperature drops below 40°F or exceeds 85°F
- 🚫 Anyone enters the mowing area
- 🚫 Any safety system shows error or warning

### Terrain Hazards

**Identify and mark these hazards**:
- Slopes steeper than 20 degrees
- Holes, depressions, or uneven ground
- Sprinkler heads and irrigation components
- Decorative objects, garden art, lawn furniture
- Tree roots, stumps, or low branches
- Property boundaries, fences, walls
- Utility markers, septic systems, well heads

## Equipment Safety

### Blade Safety

**EXTREME CAUTION**: The blade is extremely sharp and can cause severe injury or death.

**Before Blade Work**:
1. **Complete shutdown**: Ensure mower is completely powered off
2. **Disconnect power**: Remove main power connection
3. **Wait for stop**: Ensure blade has completely stopped rotating
4. **Lock out power**: Prevent accidental power-on during work

**Blade Handling**:
- Always wear cut-resistant gloves
- Handle blade by center hub only
- Keep fingers away from cutting edges
- Use proper tools for removal/installation
- Store blade safely when not installed

**Blade Maintenance**:
- Inspect weekly for damage, wear, or dullness
- Replace if cracked, chipped, or excessively worn
- Sharpen or replace when cutting quality decreases
- Ensure proper torque when reinstalling (consult manual)
- Balance blade after sharpening

### Battery and Electrical Safety

**LiFePO4 Battery Safety**:
- Handle with care - batteries are heavy (30+ lbs)
- Avoid short circuits - can cause fire or explosion
- Do not puncture, crush, or disassemble
- Keep terminals clean and covered when not connected
- Store in cool, dry location when not in use

**Electrical Safety**:
- Turn off main power before any electrical work
- Check connections regularly for corrosion or looseness
- Keep electrical components dry
- Use proper fuses and circuit protection
- Have electrical work done by qualified technician if unsure

### Motor and Mechanical Safety

**Drive Motors**:
- Keep hands and tools away from moving parts
- Ensure proper guards are in place
- Check for proper operation and unusual noises
- Lubricate according to maintenance schedule

**General Mechanical Safety**:
- Use lockout/tagout procedures during maintenance
- Support mower properly when lifting or tilting
- Check for loose bolts, worn parts, or damage
- Replace worn components before failure

## Operational Safety Procedures

### Safety Telemetry and Status Publishing

- The consolidated safety status message for the Web UI and other services is published by the Safety Service to `lawnberry/safety/status`.
- The internal Safety Monitor can optionally publish its raw status for diagnostics, but this is disabled by default to avoid duplicate traffic.
- You can tune the consolidated publish rate using the `status_publish_rate_hz` setting in `config/safety.yaml` (default: `2`). Higher values increase UI update frequency but also network traffic.
- If you enable the monitor’s debug publishing, it will emit to `lawnberry/safety/monitor_status` (not used by the UI).

Sensors and topics used by the safety stack:
- IMU: `lawnberry/sensors/imu`
- ToF left/right: `lawnberry/sensors/tof_left`, `lawnberry/sensors/tof_right`
- Environmental: `lawnberry/sensors/environmental/data` (temperature, humidity, pressure)
- GPS: `lawnberry/sensors/gps/data`
- Emergency Alerts: `lawnberry/safety/emergency` (consolidated broadcast)

### System Heartbeat and Watchdogs

To prevent false emergency triggers from watchdogs during normal operation, the safety system emits a lightweight periodic heartbeat that other services (like the EmergencyController) can consume to reset their timers.

- Topic: `lawnberry/system/heartbeat`
- Publisher: Safety system (sender `safety_system`)
- Payload type: `StatusMessage`
- Payload details: `{ "component": "safety_system", "heartbeat": true }`
- Frequency: every 2 seconds (0.5 Hz)

If a consumer requires a different frequency, keep this baseline heartbeat enabled and add complementary heartbeats from those components as needed.

Config:
- `safety.heartbeat_timeout_s` in `config/safety.yaml` controls how long the EmergencyController waits before declaring a heartbeat timeout (default 15s). Increase during bring-up if needed.

### Maintenance Warmup and Lockouts

During bring-up, some maintenance metrics (motor current, vibration, battery voltage) may not be present immediately at service start.
To prevent premature maintenance lockouts blocking operation:
- The maintenance safety subsystem observes a startup grace period during which missing data is not treated as a critical diagnostic failure.
- Defaults: `startup_grace_seconds: 180` and `allow_missing_data_during_warmup: true`.
- You can tune these in `config/safety.yaml` under a `maintenance:` section. Example:

```
maintenance:
   startup_grace_seconds: 180
   allow_missing_data_during_warmup: true
```

This does not suppress real safety issues (e.g., battery overheating) which are always treated as critical.

### Pre-Operation Safety Protocol

**Every time before starting**:

1. **Visual Inspection** (5 minutes):
   - Walk entire mowing area
   - Remove any debris, toys, tools
   - Check for new obstacles or hazards
   - Verify boundaries and no-go zones are appropriate

2. **System Check** (2 minutes):
   - Battery charge sufficient for planned operation
   - All safety systems showing green status
   - Weather forecast suitable for mowing
   - GPS lock acquired and accurate

3. **Safety Setup** (3 minutes):
   - Ensure all people and pets are clear of area
   - Set up monitoring station with web interface access
   - Have emergency stop readily accessible
   - Inform household members of mowing operation

### During Operation Safety Monitoring

**Continuous Monitoring Requirements**:
- Check mower status every 15-30 minutes
- Monitor weather conditions for changes
- Watch for people or pets approaching area
- Be ready to emergency stop at any time

**Warning Signs to Stop Operation**:
- Unusual sounds or vibrations
- Erratic movement patterns
- Safety system warnings or errors
- Weather conditions deteriorating
- Anyone approaching mowing area

### Post-Operation Safety Protocol

**After Each Mowing Session**:
1. **Verify completion**: Ensure mower has returned to home position
2. **Power down**: Allow system to shut down properly
3. **Visual inspection**: Check mower for damage or debris
4. **Clean up**: Remove any debris from mowing area
5. **Log any issues**: Note any problems for future reference

## Emergency Procedures

### Immediate Emergency Response

**If someone is injured**:
1. **Call emergency services immediately** (911)
2. **Do not move injured person** unless in immediate danger
3. **Stop all mower operations** using emergency procedures
4. **Provide first aid** only if trained to do so
5. **Clear area** of other people and pets

### Emergency Stop Procedures

**Method 1: Web Interface (Fastest)**
1. Open web interface on any connected device
2. Click large red "EMERGENCY STOP" button
3. Verify all movement has stopped
4. Keep interface open to monitor status

**Method 2: Physical Approach**
1. Approach mower from behind (never from front)
2. Lift mower slightly to trigger tilt safety stop
3. Verify blade has stopped spinning
4. Engage physical emergency stop if equipped

**Method 3: Power Disconnect**
1. Locate main power disconnect switch
2. Turn off main power
3. Wait for complete system shutdown
4. Approach mower only after complete stop

### Fire Emergency

**If mower catches fire**:
1. **Stay back** - do not approach burning mower
2. **Call fire department** immediately
3. **Evacuate area** - LiFePO4 batteries can release toxic gases
4. **Do not use water** on electrical fires
5. **Use Class C fire extinguisher** if trained and safe to do so

### Recovery After Emergency

**Before resuming operation**:
1. **Identify root cause** of emergency
2. **Repair or replace** any damaged components
3. **Test all safety systems** thoroughly
4. **Review and update** safety procedures if needed
5. **Consider additional safety measures** to prevent recurrence

## Maintenance Safety

### Routine Maintenance Safety

**Before any maintenance**:
- Complete system shutdown and power disconnect
- Allow moving parts to come to complete stop
- Use proper tools and follow procedures
- Work in well-lit area with adequate space

### Seasonal Safety Considerations

**Spring Startup**:
- Inspect all safety systems after winter storage
- Check for damage from weather or pests
- Test emergency stop and safety sensors
- Update software and safety protocols

**Fall Shutdown**:
- Clean all debris from mower
- Store in dry, secure location
- Disconnect and store battery properly
- Cover or protect from weather

### Professional Service Requirements

**Seek professional service for**:
- Electrical system repairs
- Motor or drive system problems
- Safety system malfunctions
- Structural damage or modifications
- Any repair you're not comfortable performing safely

## Legal and Insurance Considerations

### Liability and Insurance

**Check with your insurance provider**:
- Homeowner's insurance coverage for autonomous equipment
- Liability coverage for property damage
- Additional riders that may be needed
- Requirements for safety measures or certifications

### Local Regulations

**Research local requirements**:
- City/county ordinances regarding robotic lawn equipment
- Noise restrictions and permitted operating hours
- Property line setback requirements
- Registration or permit requirements

### Neighbor Considerations

**Be a good neighbor**:
- Inform adjacent neighbors of your mowing schedule
- Ensure mower stays within your property boundaries
- Respect quiet hours and noise ordinances
- Address any concerns promptly and professionally

## Safety Training and Education

### Family Safety Training

**All household members should know**:
- How to identify when mower is operating
- Emergency stop procedures
- Safe areas vs. mowing areas
- What to do if they see someone in danger

### Regular Safety Reviews

**Monthly safety discussions should cover**:
- Any near-misses or safety concerns
- Changes to mowing area or schedule
- Updates to safety procedures
- Equipment condition and maintenance needs

### Seasonal Safety Updates

**Review and update safety measures**:
- Changes in yard layout or landscaping
- New family members, pets, or neighbors
- Equipment modifications or upgrades
- Lessons learned from previous season

## Safety Equipment Recommendations

### Required Safety Equipment

- **First aid kit** easily accessible during operation
- **Fire extinguisher** (Class C for electrical fires)
- **Emergency contact list** posted visibly
- **Proper tools** for maintenance and emergency repairs

### Optional Safety Enhancements

- **Motion detectors** with automatic mower stop
- **Perimeter barriers** or fencing
- **Warning signs** and lights
- **Security cameras** for remote monitoring
- **Backup communication** methods (cell phone, radio)

## Safety Checklist Summary

Print and laminate this checklist for field use:

### Pre-Operation Safety Checklist
- [ ] Area cleared of people, pets, and objects
- [ ] Weather conditions safe and dry
- [ ] Blade sharp and properly installed
- [ ] All safety systems tested and functional
- [ ] Emergency stop procedures reviewed
- [ ] Monitoring station prepared

### During Operation Checklist
- [ ] Regular status monitoring every 15-30 minutes
- [ ] Weather conditions remain suitable
- [ ] No unauthorized persons in mowing area
- [ ] Emergency stop readily accessible
- [ ] Unusual sounds or behaviors addressed immediately

### Post-Operation Checklist
- [ ] Mower returned safely to home position
- [ ] System properly shut down
- [ ] Area inspected for any issues
- [ ] Equipment inspected for damage
- [ ] Any problems documented

---

## Final Safety Reminders

**Remember**: The LawnBerryPi is a powerful tool that demands respect and proper safety procedures. Never become complacent with safety - each operation should be treated with the same caution as the first.

**Key Principles**:
- Always maintain situational awareness
- Plan for emergencies before they happen
- When in doubt, stop operation and assess
- Safety systems are there for protection - never bypass them
- Regular maintenance prevents safety hazards

**Your safety and the safety of others is always the highest priority. No lawn is worth risking injury or life.**

---

*This safety guide must be reviewed and understood by all users before operating the LawnBerryPi system.*

*Safety Guide - Part of LawnBerryPi Documentation v1.0*
