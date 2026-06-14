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

// ---------------------------------------------------------------------------
// Break of Structure event
// ---------------------------------------------------------------------------

export type BosStatus    = 'valid' | 'pending' | 'invalid'
export type BosDirection = 'bullish' | 'bearish'

export interface BosEvent {
  status:                      BosStatus
  direction:                   BosDirection
  structureScope:              StructureLevel
  breakLevel:                  number
  protectedLevel:              number
  breakCandleIndex:            number
  breakCandleTimestamp:        string
  confirmationLevel?:          number
  confirmationCandleIndex?:    number
  confirmationCandleTimestamp?: string
  invalidationCandleIndex?:    number
  invalidationCandleTimestamp?: string
  eventType:                   'bos'
  eventEffect:                 'continuation'
}

// ---------------------------------------------------------------------------
// Change of Character event
// ---------------------------------------------------------------------------

export type ChochDirection = 'bullish' | 'bearish'

export interface ChochEvent {
  direction:                  ChochDirection
  structureScope:             StructureLevel
  protectedLevel:             number
  breakCandleIndex:           number
  breakCandleTimestamp:       string
  structureReferenceIndex:    number
  structureReferenceTimestamp: string
  referenceStructureType:     'HL' | 'LH'
  violatedTrend:              'uptrend' | 'downtrend'
  eventType:                  'choch'
  status:                     'valid'
  eventEffect:                'transition'
}

// ---------------------------------------------------------------------------
// Aggregate result returned by the market-structure API call
// ---------------------------------------------------------------------------

export interface StructureResult {
  minorPoints:  StructurePoint[]
  minorLegs:    StructureLeg[]
  mainPoints:   StructurePoint[]
  mainLegs:     StructureLeg[]
  debugEvents:  StructureDebugEvent[]
  bosEvents:    BosEvent[]
  chochEvents:  ChochEvent[]
}

export interface StructureDisplay {
  showMinorStructure: boolean
  showMainStructure: boolean
  showStructureLabels: boolean
  showDebugMetadata: boolean
}
