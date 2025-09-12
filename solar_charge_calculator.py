# Solar Charging Time Calculator

# Battery and Controller Specifications
battery_voltage = 12            # Volts
battery_capacity_ah = 30        # Ampere-hours
controller_max_current = 20     # Amps

# Define solar panels with Voltage and Wattage
solar_panels = [
    {
        'name': 'Offgridtec OLP 30W',
        'voltage': 23,
        'power_watt': 30
    },
    {
        'name': 'Portable Power Tech 30W',
        'voltage': 18,  # Typically ~18V for "12V panels"
        'power_watt': 30
    },
    # Add additional panels here
]

# Efficiency assumptions
charge_controller_efficiency = 0.90
battery_charge_efficiency = 0.95

# Calculate estimated charging times
for panel in solar_panels:
    panel_current = panel['power_watt'] / panel['voltage']  # Panel current (Amps)
    usable_current = min(panel_current, controller_max_current)  # Controller current limit

    effective_current = usable_current * charge_controller_efficiency * battery_charge_efficiency

    charge_time_hours = battery_capacity_ah / effective_current

    print(f"Panel: {panel['name']}")
    print(f"  Panel Voltage: {panel['voltage']} V")
    print(f"  Panel Current: {panel_current:.2f} A")
    print(f"  Effective Charging Current: {effective_current:.2f} A")
    print(f"  Estimated Charging Time: {charge_time_hours:.2f} hours\n")
