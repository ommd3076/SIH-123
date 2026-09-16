# Warehouse Map Specification

This document details the topological graph specification used by the AMR fleet simulation.

## Coordinate System & Units
- Coordinates \(x, y)\ are expressed in meters from the warehouse origin \(0, 0)\.
- Speeds are defined in m/s (default wide aisle: 1.6 m/s, narrow aisle: 1.0 m/s).

## Graph Components
1. **Junctions (\J01\ - \J40\)**: Key traffic routing vertices and intersection arbitration points.
2. **Narrow Aisles (\NA1\ - \NA7\)**: Single-file storage corridors governed by space-time reservations and direction gates.
3. **Bays (\B11\ - \B72\)**: Storage pick/drop stations along narrow aisles.
4. **Chargers (\C1\, \C2\)**: Automated charging stations with dedicated approach links.
5. **Staging / Pick & Drop Zones**: Outbound staging (\O1\, \O2\), pickup stations (\P1\ - \P3\), and drop points (\D1\ - \D3\).
