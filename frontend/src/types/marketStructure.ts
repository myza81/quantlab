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
// Lineage metadata (RESEARCH-TOOL-LINEAGE-GUARD-1)
// ---------------------------------------------------------------------------

/** Lineage for a versioned research tool execution (root, e.g. structure engine). */
export interface ToolLineage {
  toolDomain:       string   // "market_structure"
  toolId:           string   // "minor_structure_v3"
  versionId:        string
  humanName:        string   // "Container Breakout Minor Structure"
  lifecycleStatus:  string   // "production" | "experimental"
  implementationRef: string  // "backend/tools/market_structure_v3.py::MinorStructureV3Engine"
}

/** Lineage for a tool whose input is another tool's output (e.g. BoS, CHoCH). */
export interface DerivedToolLineage {
  toolDomain:       string   // "structure_event"
  toolId:           string   // "bos_detection" | "choch_detection"
  parentToolDomain: string   // "market_structure"
  parentEngineId:   string   // must equal structureLineage.toolId
}

// ---------------------------------------------------------------------------
// Market bias (experimental geometric engine)
// ---------------------------------------------------------------------------

export interface MarketBias {
  engine:        string
  bias:          'BULLISH' | 'BEARISH' | 'SIDEWAY'
  condition:     string   // "CONTINUATION" | "REVERSAL" | "CONSOLIDATION" | "VOLATILE" | "INSUFFICIENT_DATA"
  reason:        string
  pivotsUsed:    number[]
  currentClose:  number
  boundaries:    { support: number | null; resistance: number | null }
}

// ---------------------------------------------------------------------------
// Experimental pivot-triplet BoS event (Scenario 1: bullish only)
// ---------------------------------------------------------------------------

export interface ExperimentalBosEvent {
  direction:             'bullish'
  p1BarIndex:            number
  p1Price:               number
  p1Timestamp:           string
  p2BarIndex:            number
  p2Price:               number
  p2Timestamp:           string
  p3BarIndex:            number
  p3Price:               number
  p3Timestamp:           string
  breakCandleIndex:      number
  breakCandleTimestamp:  string
  brokenLevel:           number
}

// ---------------------------------------------------------------------------
// Aggregate result returned by the market-structure API call
// ---------------------------------------------------------------------------

export interface StructureResult {
  minorPoints:           StructurePoint[]
  minorLegs:             StructureLeg[]
  mainPoints:            StructurePoint[]
  mainLegs:              StructureLeg[]
  debugEvents:           StructureDebugEvent[]
  bosEvents:             BosEvent[]
  chochEvents:           ChochEvent[]
  experimentalBosEvents: ExperimentalBosEvent[]
  marketBias?:           MarketBias
  structureLineage?:     ToolLineage
  bosLineage?:           DerivedToolLineage
  chochLineage?:         DerivedToolLineage
}

export interface StructureDisplay {
  showMinorStructure: boolean
  showMainStructure: boolean
  showStructureLabels: boolean
  showDebugMetadata: boolean
}
