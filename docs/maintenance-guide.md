# LawnBerryPi Maintenance Guide

Regular maintenance keeps your LawnBerryPi operating safely, efficiently, and reliably. This guide provides step-by-step maintenance procedures for users of all technical backgrounds.

## Maintenance Schedule Overview

| Frequency | Tasks | Time Required |
|-----------|-------|---------------|
| **Daily** | Status check, area inspection | 5 minutes |
| **Weekly** | Cleaning, blade inspection | 15-30 minutes |
| **Monthly** | Deep cleaning, calibration | 1-2 hours |
| **Seasonally** | Comprehensive inspection | 2-3 hours |
| **Annually** | Professional service, major components | 4-6 hours |

## Daily Maintenance (5 minutes)

### Quick Status Check

**Visual Inspection**:
- [ ] Battery charge level > 20%
- [ ] No visible damage to mower body
- [ ] Wheels turn freely, no debris stuck
- [ ] Camera lens clean and unobstructed

**Dashboard Check**:
- [ ] All system status indicators green
- [ ] GPS showing accurate location
- [ ] Weather data current and accurate
- [ ] No error messages or warnings

**Area Inspection**:
- [ ] Mowing area clear of new obstacles
- [ ] No toys, tools, or debris in yard
- [ ] Sprinkler systems off during mowing hours
- [ ] No changes to landscaping affecting boundaries

## Weekly Maintenance (15-30 minutes)

### Cleaning and Basic Inspection

**⚠️ Safety First**: Ensure mower is completely powered off before maintenance.

#### 1. External Cleaning

**Tools Needed**:
- Soft brush or cloth
- Garden hose with gentle spray
- Compressed air (optional)
- Microfiber cloth

**Procedure**:
1. **Power off completely**: Disconnect main power
2. **Remove loose debris**: 
   - Use brush to remove grass clippings from body
   - Clear debris from wheels and undercarriage
   - Remove leaves, twigs, or other material
3. **Gentle washing**:
   - Use damp cloth to wipe exterior surfaces
   - **Avoid**: Direct water spray on electronics
   - Clean around sensors carefully
4. **Dry thoroughly**: Use microfiber cloth to prevent water spots

#### 2. Blade Inspection and Cleaning

**⚠️ DANGER**: Blade is extremely sharp. Use proper safety equipment.

**Safety Equipment Required**:
- Cut-resistant gloves
- Safety glasses
- Proper tools (as specified in manual)

**Inspection Steps**:
1. **Secure mower**: Ensure it cannot accidentally start
2. **Examine blade condition**:
   - [ ] Sharp cutting edge (no chips or major nicks)
   - [ ] Securely attached to motor shaft
   - [ ] Balanced (no wobble when spun by hand)
   - [ ] No cracks or structural damage
3. **Clean blade area**:
   - Remove grass buildup around blade housing
   - Clear ventilation holes in deck
   - Check for belt wear (if belt-driven)

**Blade Replacement Indicators**:
- Cutting edge is dull or damaged
- Visible cracks in blade material
- Blade wobbles when rotated by hand
- Poor cutting performance despite proper operation

#### 3. Sensor Cleaning

**Camera Lens**:
- Use microfiber cloth to gently clean
- Remove water spots, dust, or debris
- Check for scratches that might affect vision

**ToF Distance Sensors**:
- Clean sensor windows with soft, dry cloth
- Remove grass clippings or dirt buildup
- Test sensor readings after cleaning

**Environmental Sensor (BME280)**:
- Ensure sensor housing is clean and dry
- Remove any debris blocking ventilation
- Check readings for accuracy

#### 4. Wheel and Drive System

**Wheel Inspection**:
- [ ] Wheels rotate freely without binding
- [ ] No grass wrapped around axles
- [ ] Tire tread in good condition
- [ ] No visible damage to wheel hubs

**Drive System Check**:
- Listen for unusual noises during manual wheel rotation
- Check for excessive play in drive components
- Ensure motor mounting is secure

## Monthly Maintenance (1-2 hours)

### Comprehensive System Check

#### 1. Battery System Maintenance

**Battery Inspection**:
- [ ] Clean terminals (remove corrosion with baking soda solution)
- [ ] Check connections are tight and secure
- [ ] Inspect for physical damage, swelling, or leaks
- [ ] Verify charging performance

**Battery Performance Test**:
1. **Full charge test**: Charge battery to 100% and note time required
2. **Load test**: Run mower for known time/distance and measure consumption
3. **Capacity check**: Compare current performance to baseline
4. **Document results**: Track battery health over time

**Solar Panel Maintenance**:
- Clean solar panel surface with soap and water
- Check mounting hardware for tightness
- Inspect wiring for damage or wear
- Verify charge controller operation

#### 2. Navigation System Calibration

**GPS System Check**:
1. **Satellite reception test**:
   - Place mower in open area
   - Monitor satellite count and signal strength
   - Record time to first fix and accuracy
2. **Position accuracy test**:
   - Compare GPS position to known reference points
   - Check for consistent position readings
   - Verify boundary following accuracy

**IMU Calibration**:
1. **Access calibration mode**: Settings → Hardware → IMU Calibration
2. **Follow calibration routine**:
   - Slow figure-8 motions
   - Rotate through all axes
   - Complete calibration sequence
3. **Test compass accuracy**: Verify directional readings

**Obstacle Detection Calibration**:
- Test sensors at various distances (0.5m, 1m, 2m)
- Adjust sensitivity settings if needed
- Verify reliable detection of standard obstacles

#### 3. Software and Configuration Maintenance

**Software Updates**:
1. **Check for updates**: Settings → System → Check for Updates
2. **Backup configuration**: Export current settings before updating
3. **Install updates**: Follow update procedure
4. **Test functionality**: Verify all systems work after update

**Configuration Backup**:
- Export boundary definitions
- Save schedule configurations
- Backup customization settings
- Store API keys and credentials securely

**Log File Maintenance**:
- Review system logs for errors or warnings
- Archive old log files to free space
- Clear diagnostic data if needed

#### 4. Performance Analysis

**Mowing Efficiency Review**:
- Analyze mowing patterns and coverage
- Identify areas of inefficiency
- Adjust patterns or boundaries if needed
- Optimize for better battery usage

**Statistical Analysis**:
- Review monthly mowing statistics
- Compare performance trends
- Identify maintenance needs based on usage
- Plan for seasonal adjustments

## Seasonal Maintenance (2-3 hours)

### Spring Startup Procedure

**Pre-Season Inspection**:
1. **Winter storage assessment**:
   - Check for pest damage or nesting
   - Inspect for moisture damage
   - Verify all components are present
2. **Mechanical inspection**:
   - Lubricate moving parts per schedule
   - Check belt tension and condition
   - Inspect motor mountings and hardware
3. **Electrical system check**:
   - Test all connections for corrosion
   - Verify proper voltage levels
   - Check safety system operation

**System Recommissioning**:
1. **Battery conditioning**:
   - Perform full charge/discharge cycle
   - Check capacity against baseline
   - Replace if capacity < 80% of original
2. **Calibration renewal**:
   - Recalibrate all sensors
   - Update GPS baseline
   - Test obstacle detection accuracy
3. **Boundary verification**:
   - Walk boundaries to check for landscape changes
   - Update no-go zones for new obstacles
   - Adjust for seasonal landscaping

### Fall Winterization Procedure

**Pre-Storage Preparation**:
1. **Thorough cleaning**:
   - Remove all grass clippings and debris
   - Clean and dry all surfaces
   - Apply protective coating if recommended
2. **Fluid changes** (if applicable):
   - Replace hydraulic fluids
   - Top off lubricants
   - Check fluid levels and condition
3. **Battery winterization**:
   - Charge to storage level (typically 50-70%)
   - Disconnect from system
   - Store in climate-controlled environment

**Storage Setup**:
1. **Protective storage**:
   - Cover mower to prevent dust accumulation
   - Ensure ventilation to prevent condensation
   - Protect from extreme temperatures
2. **Documentation**:
   - Record final maintenance performed
   - Note any issues to address next season
   - Update maintenance log

## Annual Maintenance (4-6 hours)

### Professional Service Items

**Items requiring professional service**:
- Motor bearing replacement
- Drive system overhaul
- Electrical system inspection
- Structural integrity assessment
- Warranty service items

### Major Component Replacement

**Wear Items Replacement Schedule**:
- **Blades**: Replace annually or when dull
- **Belts**: Every 2-3 years or as needed
- **Air filters**: Annually (if equipped)
- **Lubricants**: Per manufacturer schedule

**Component Lifecycle Management**:
- Track component hours/cycles
- Plan replacement before failure
- Source replacement parts in advance
- Budget for major replacements

### System Upgrade Considerations

**Annual Review Items**:
- Software capabilities and new features
- Hardware upgrade opportunities
- Efficiency improvements available
- Safety system enhancements

## Troubleshooting Maintenance Issues

### Common Maintenance Problems

**Grass Buildup**:
- **Cause**: Mowing wet grass, dull blade
- **Solution**: Clean thoroughly, sharpen blade, adjust schedule
- **Prevention**: Mow only in dry conditions

**Sensor Drift**:
- **Cause**: Temperature changes, component aging
- **Solution**: Recalibration, sensor replacement if needed
- **Prevention**: Regular calibration schedule

**Battery Degradation**:
- **Cause**: Normal aging, improper charging, extreme temperatures
- **Solution**: Battery replacement, charging system check
- **Prevention**: Proper storage, avoid deep discharge

**Navigation Accuracy Issues**:
- **Cause**: GPS interference, compass calibration, boundary drift
- **Solution**: Site survey, recalibration, boundary update
- **Prevention**: Regular accuracy testing

### Maintenance Safety Procedures

**Before Any Maintenance**:
1. **Complete shutdown**: Turn off all power systems
2. **Lockout procedures**: Prevent accidental startup
3. **Safety equipment**: Use appropriate PPE
4. **Work environment**: Ensure adequate lighting and space

**During Maintenance**:
- Follow procedures exactly as written
- Use only specified tools and parts
- Document any deviations or issues
- Stop if unsure about any procedure

**After Maintenance**:
- Test all systems before returning to service
- Update maintenance records
- Verify safety systems are functional
- Monitor initial operation closely

## Maintenance Record Keeping

### Required Documentation

**Maintenance Log**:
- Date and type of maintenance performed
- Parts replaced or serviced
- Issues found and corrected
- Performance measurements
- Next maintenance due dates

**Performance Baseline**:
- Initial system capabilities and measurements
- Degradation trends over time
- Efficiency metrics
- Battery performance data

### Digital Maintenance Tracking

**Use built-in system features**:
- Maintenance reminder system
- Performance data logging
- Error code history
- Service interval tracking

**External record keeping**:
- Backup critical maintenance data
- Photo documentation of issues
- Warranty and service records
- Parts inventory and costs

## Seasonal Maintenance Checklist

### Spring Checklist
- [ ] Winter storage inspection complete
- [ ] Battery capacity test passed
- [ ] All sensors calibrated
- [ ] Boundaries verified and updated
- [ ] Safety systems tested
- [ ] Software updated to current version
- [ ] Blade sharpened or replaced
- [ ] First mow test completed successfully

### Summer Checklist
- [ ] Heat stress monitoring implemented
- [ ] Extra cleaning due to heavy use
- [ ] Battery performance monitored closely
- [ ] Blade wear checked more frequently
- [ ] Irrigation system coordination verified
- [ ] Peak usage efficiency optimization

### Fall Checklist
- [ ] Leaf management strategy implemented
- [ ] Pre-winter deep cleaning completed
- [ ] Battery winterization performed
- [ ] Protective storage prepared
- [ ] Maintenance summary documented
- [ ] Next season planning completed

### Winter Checklist
- [ ] Storage conditions monitored
- [ ] Battery maintenance performed
- [ ] Planning for next season upgrades
- [ ] Maintenance schedule review and update
- [ ] Parts inventory and ordering
- [ ] Documentation organization

## Maintenance Tools and Supplies

### Basic Tool Kit
- Standard metric and imperial wrenches
- Screwdrivers (Phillips and flathead)
- Multimeter for electrical testing
- Torque wrench for proper bolt tension
- Cleaning supplies and brushes

### Specialized Tools (as needed)
- Blade removal and installation tools
- GPS accuracy measurement equipment
- Battery load tester
- Compressed air system
- Protective equipment (gloves, glasses)

### Replacement Parts Inventory
- Spare blades (2-3 units)
- Common fasteners and hardware
- Cleaning and lubrication supplies
- Basic electrical components (fuses, connectors)
- Weather protection materials

---

**Regular maintenance is the key to safe, reliable, and efficient operation of your LawnBerryPi. When in doubt, consult the manufacturer or seek professional service.**

*Maintenance Guide - Part of LawnBerryPi Documentation v1.0*
