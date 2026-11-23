# Generator Monitoring System

The site uses ComAp InteliGen 200 controllers, one per generator, with
InteliATS PWR controllers on the feeder outputs, monitored from a PC running
InteliSCADA.

Values reported per generator:
  active power (kW), load percentage, frequency,
  current on L1 / L2 / L3, voltage L1-N / L2-N / L3-N, power factor,
  engine run hours, and where the ECU link is connected:
  fuel rate (L/h), coolant temperature, oil pressure, engine speed.

IMPORTANT LIMITATION: on this site the ECU link is connected on only one
generator. The remaining units report no fuel, temperature, pressure or RPM
data. Any fuel-efficiency or predictive-maintenance analysis is therefore
limited to that single generator until the other ECU links are wired.

Fuel efficiency is expressed as litres per kWh. A healthy diesel generator
at 70 to 85 percent load consumes roughly 0.25 to 0.30 L/kWh. A rising ratio
over time indicates engine wear, fouled injectors, or fuel being removed.

Generators do not run continuously. Running hours vary with season and
demand, typically 10 to 18 hours per day, concentrated in the evening.

Common alarm messages include maintenance timer warnings, ECU yellow lamp,
output-off warnings, overload warnings and low battery.
