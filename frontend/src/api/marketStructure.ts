/**
 * Market Structure API client — MS-2 / VIZ-1.
 *
 * POSTs already-loaded OHLCV candles to the backend engine.
 * No provider re-fetch; the computation is pure and deterministic.
 * Returns structure points/legs, BoS events, and CHoCH events.
 */
import { authedFetch } from './client'
import type { OHLCVCandle } from './marketData'
import type {
  StructureResult,
  StructurePoint,
  StructureLeg,
  StructureDebugEvent,
  StructureLevel,
  PointKind,
  StructureDirection,
  BosEvent,
  BosStatus,
  BosDirection,
  ChochEvent,
  ChochDirection,
  ExperimentalBosEvent,
  MarketBias,
  ToolLineage,
  DerivedToolLineage,
} from '../types/marketStructure'

// ---------------------------------------------------------------------------
// Raw backend shapes (snake_case)
// ---------------------------------------------------------------------------

interface RawStructurePoint {
  id: string
  level: string
  kind: string
  timestamp: string
  bar_index: number
  price: number
  source: string
  confirmed: boolean
}

interface RawStructureLeg {
  id: string
  level: string
  from_point_id: string
  to_point_id: string
  direction: string
  start_bar_index: number
  end_bar_index: number
  start_price: number
  end_price: number
}

interface RawDebugEvent {
  bar_index: number
  timestamp: string
  candle_relationship: string
  previous_direction: string | null
  new_direction: string | null
  action: string
  reason: string
  affected_level: string
}

interface RawBosEvent {
  status: string
  direction: string
  structure_scope: string
  break_level: number
  protected_level: number
  break_candle_index: number
  break_candle_timestamp: string
  confirmation_level: number | null
  confirmation_candle_index: number | null
  confirmation_candle_timestamp: string | null
  invalidation_candle_index: number | null
  invalidation_candle_timestamp: string | null
  event_type: string
  event_effect: string
}

interface RawChochEvent {
  direction: string
  structure_scope: string
  protected_level: number
  break_candle_index: number
  break_candle_timestamp: string
  structure_reference_index: number
  structure_reference_timestamp: string
  reference_structure_type: string
  violated_trend: string
  event_type: string
  status: string
  event_effect: string
}

interface RawToolLineage {
  tool_domain:        string
  tool_id:            string
  version_id:         string
  human_name:         string
  lifecycle_status:   string
  implementation_ref: string
}

interface RawDerivedToolLineage {
  tool_domain:        string
  tool_id:            string
  parent_tool_domain: string
  parent_engine_id:   string
}

interface RawMarketBias {
  engine:        string
  bias:          string
  condition:     string
  reason:        string
  pivots_used:   number[]
  current_close: number
  boundaries:    { support: number | null; resistance: number | null }
}

interface RawExperimentalBosEvent {
  direction:              string
  p1_bar_index:           number
  p1_price:               number
  p1_timestamp:           string
  p2_bar_index:           number
  p2_price:               number
  p2_timestamp:           string
  p3_bar_index:           number
  p3_price:               number
  p3_timestamp:           string
  break_candle_index:     number
  break_candle_timestamp: string
  broken_level:           number
}

interface RawMarketStructureResponse {
  minor_points:             RawStructurePoint[]
  minor_legs:               RawStructureLeg[]
  main_points:              RawStructurePoint[]
  main_legs:                RawStructureLeg[]
  debug_events:             RawDebugEvent[]
  bos_events:               RawBosEvent[]
  choch_events:             RawChochEvent[]
  experimental_bos_events?: RawExperimentalBosEvent[]
  market_bias?:             RawMarketBias
  structure_lineage?:       RawToolLineage
  bos_lineage?:             RawDerivedToolLineage
  choch_lineage?:           RawDerivedToolLineage
}

// ---------------------------------------------------------------------------
// Mapping helpers (snake_case → camelCase)
// ---------------------------------------------------------------------------

function mapPoint(raw: RawStructurePoint): StructurePoint {
  return {
    id: raw.id,
    level: raw.level as StructureLevel,
    kind: raw.kind as PointKind,
    timestamp: raw.timestamp,
    barIndex: raw.bar_index,
    price: raw.price,
    source: raw.source,
    confirmed: raw.confirmed,
  }
}

function mapLeg(raw: RawStructureLeg): StructureLeg {
  return {
    id: raw.id,
    level: raw.level as StructureLevel,
    fromPointId: raw.from_point_id,
    toPointId: raw.to_point_id,
    direction: raw.direction as StructureDirection,
    startBarIndex: raw.start_bar_index,
    endBarIndex: raw.end_bar_index,
    startPrice: raw.start_price,
    endPrice: raw.end_price,
  }
}

function mapDebugEvent(raw: RawDebugEvent): StructureDebugEvent {
  return {
    barIndex: raw.bar_index,
    timestamp: raw.timestamp,
    candleRelationship: raw.candle_relationship,
    previousDirection: (raw.previous_direction as StructureDirection | undefined) ?? undefined,
    newDirection: (raw.new_direction as StructureDirection | undefined) ?? undefined,
    action: raw.action,
    reason: raw.reason,
    affectedLevel: raw.affected_level,
  }
}

function mapBosEvent(raw: RawBosEvent): BosEvent {
  return {
    status:                      raw.status as BosStatus,
    direction:                   raw.direction as BosDirection,
    structureScope:              raw.structure_scope as StructureLevel,
    breakLevel:                  raw.break_level,
    protectedLevel:              raw.protected_level,
    breakCandleIndex:            raw.break_candle_index,
    breakCandleTimestamp:        raw.break_candle_timestamp,
    confirmationLevel:           raw.confirmation_level ?? undefined,
    confirmationCandleIndex:     raw.confirmation_candle_index ?? undefined,
    confirmationCandleTimestamp: raw.confirmation_candle_timestamp ?? undefined,
    invalidationCandleIndex:     raw.invalidation_candle_index ?? undefined,
    invalidationCandleTimestamp: raw.invalidation_candle_timestamp ?? undefined,
    eventType:                   'bos',
    eventEffect:                 'continuation',
  }
}

function mapChochEvent(raw: RawChochEvent): ChochEvent {
  return {
    direction:                   raw.direction as ChochDirection,
    structureScope:              raw.structure_scope as StructureLevel,
    protectedLevel:              raw.protected_level,
    breakCandleIndex:            raw.break_candle_index,
    breakCandleTimestamp:        raw.break_candle_timestamp,
    structureReferenceIndex:     raw.structure_reference_index,
    structureReferenceTimestamp: raw.structure_reference_timestamp,
    referenceStructureType:      raw.reference_structure_type as 'HL' | 'LH',
    violatedTrend:               raw.violated_trend as 'uptrend' | 'downtrend',
    eventType:                   'choch',
    status:                      'valid',
    eventEffect:                 'transition',
  }
}

function mapExperimentalBosEvent(raw: RawExperimentalBosEvent): ExperimentalBosEvent {
  return {
    direction:            raw.direction as 'bullish',
    p1BarIndex:           raw.p1_bar_index,
    p1Price:              raw.p1_price,
    p1Timestamp:          raw.p1_timestamp,
    p2BarIndex:           raw.p2_bar_index,
    p2Price:              raw.p2_price,
    p2Timestamp:          raw.p2_timestamp,
    p3BarIndex:           raw.p3_bar_index,
    p3Price:              raw.p3_price,
    p3Timestamp:          raw.p3_timestamp,
    breakCandleIndex:     raw.break_candle_index,
    breakCandleTimestamp: raw.break_candle_timestamp,
    brokenLevel:          raw.broken_level,
  }
}

function mapMarketBias(raw: RawMarketBias): MarketBias {
  return {
    engine:       raw.engine,
    bias:         raw.bias as MarketBias['bias'],
    condition:    raw.condition,
    reason:       raw.reason,
    pivotsUsed:   raw.pivots_used,
    currentClose: raw.current_close,
    boundaries:   raw.boundaries,
  }
}

function mapToolLineage(raw: RawToolLineage): ToolLineage {
  return {
    toolDomain:        raw.tool_domain,
    toolId:            raw.tool_id,
    versionId:         raw.version_id,
    humanName:         raw.human_name,
    lifecycleStatus:   raw.lifecycle_status,
    implementationRef: raw.implementation_ref,
  }
}

function mapDerivedToolLineage(raw: RawDerivedToolLineage): DerivedToolLineage {
  return {
    toolDomain:       raw.tool_domain,
    toolId:           raw.tool_id,
    parentToolDomain: raw.parent_tool_domain,
    parentEngineId:   raw.parent_engine_id,
  }
}

function mapResponse(raw: RawMarketStructureResponse): StructureResult {
  return {
    minorPoints:           raw.minor_points.map(mapPoint),
    minorLegs:             raw.minor_legs.map(mapLeg),
    mainPoints:            raw.main_points.map(mapPoint),
    mainLegs:              raw.main_legs.map(mapLeg),
    debugEvents:           raw.debug_events.map(mapDebugEvent),
    bosEvents:             (raw.bos_events             ?? []).map(mapBosEvent),
    chochEvents:           (raw.choch_events            ?? []).map(mapChochEvent),
    experimentalBosEvents: (raw.experimental_bos_events ?? []).map(mapExperimentalBosEvent),
    marketBias:            raw.market_bias ? mapMarketBias(raw.market_bias) : undefined,
    structureLineage:      raw.structure_lineage ? mapToolLineage(raw.structure_lineage)           : undefined,
    bosLineage:            raw.bos_lineage       ? mapDerivedToolLineage(raw.bos_lineage)          : undefined,
    chochLineage:          raw.choch_lineage     ? mapDerivedToolLineage(raw.choch_lineage)        : undefined,
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Compute market structure (points/legs, BoS, CHoCH) for already-loaded candles.
 *
 * Candles are sorted chronologically before posting so bar_index in the
 * response reliably maps to the sorted position.
 */
export async function fetchMarketStructure(
  candles: OHLCVCandle[],
  engineId?: string,
): Promise<StructureResult> {
  const sorted = [...candles].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  )

  const body: Record<string, unknown> = { candles: sorted }
  if (engineId && engineId !== 'minor_structure_v1') {
    body.engine_id = engineId
  }

  const raw = await authedFetch('/chart/market-structure', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  }).then(r => r.json() as Promise<RawMarketStructureResponse>)

  return mapResponse(raw)
}
