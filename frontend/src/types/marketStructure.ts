/**
 * Market Structure Types — Visual verification tool for chart rendering.
 *
 * These types model the visual representation of market structure on the chart.
 * No trading signals, strategy logic, or execution occurs here.
 */

export type StructureLevel = 'minor' | 'main'
export type PointKind = 'L' | 'H' | 'LL' | 'LH' | 'HH' | 'HL' | 'unknown'
export type StructureDirection = 'up' | 'down'

export interface StructurePoint {
  id: string
  level: StructureLevel
  kind: PointKind
  timestamp: string        // ISO 8601 UTC
  barIndex: number
  price: number
  source: string          // "price", "minor", "main"
  confirmed: boolean
}

export interface StructureLeg {
  id: string
  level: StructureLevel
  fromPointId: string
  toPointId: string
  direction: StructureDirection
  startBarIndex: number
  endBarIndex: number
  startPrice: number
  endPrice: number
}

export interface StructureDebugEvent {
  barIndex: number
  timestamp: string
  candleRelationship: string
  previousDirection?: StructureDirection
  newDirection?: StructureDirection
  action: string
  reason: string
  affectedLevel: string
}

export interface StructureResult {
  minorPoints: StructurePoint[]
  minorLegs: StructureLeg[]
  mainPoints: StructurePoint[]
  mainLegs: StructureLeg[]
  debugEvents: StructureDebugEvent[]
}

export interface StructureDisplay {
  showMinorStructure: boolean
  showMainStructure: boolean
  showStructureLabels: boolean
  showDebugMetadata: boolean
}
