/**
 * Tests for auto-generated tool instance IDs and display names — Strategy-UX-1A.
 */
import { describe, it, expect } from 'vitest'
import {
  generateInstanceIdBase,
  ensureUniqueInstanceId,
  generateDisplayName,
} from '../toolIdentityGeneration'

describe('toolIdentityGeneration', () => {
  describe('generateInstanceIdBase', () => {
    it('generates SMA ID from period and source', () => {
      const id = generateInstanceIdBase('sma', { period: 21, source: 'close' })
      expect(id).toBe('sma_21_close')
    })

    it('generates EMA ID from period and source', () => {
      const id = generateInstanceIdBase('ema', { period: 9, source: 'close' })
      expect(id).toBe('ema_9_close')
    })

    it('generates RSI ID from period only', () => {
      const id = generateInstanceIdBase('rsi', { period: 14 })
      expect(id).toBe('rsi_14')
    })

    it('generates MACD ID from three periods', () => {
      const id = generateInstanceIdBase('macd', {
        fast_period: 12,
        slow_period: 26,
        signal_period: 9,
      })
      expect(id).toBe('macd_12_26_9')
    })

    it('generates Bollinger ID from period and std_dev', () => {
      const id = generateInstanceIdBase('bollinger', { period: 20, std_dev: 2 })
      expect(id).toBe('bollinger_20_2')
    })

    it('skips missing optional parameters', () => {
      const id = generateInstanceIdBase('sma', { period: 21 })
      expect(id).toBe('sma_21')
    })

    it('returns tool_id for unknown tool', () => {
      const id = generateInstanceIdBase('unknown_tool', { param: 123 })
      expect(id).toBe('unknown_tool')
    })

    it('handles float parameters', () => {
      const id = generateInstanceIdBase('bollinger', { period: 20, std_dev: 2.5 })
      expect(id).toBe('bollinger_20_2.5')
    })
  })

  describe('ensureUniqueInstanceId', () => {
    it('returns base ID if not in existing set', () => {
      const existing = new Set(['sma_10', 'ema_20'])
      const unique = ensureUniqueInstanceId('sma_21_close', existing)
      expect(unique).toBe('sma_21_close')
    })

    it('appends _2 if base ID exists', () => {
      const existing = new Set(['sma_21_close'])
      const unique = ensureUniqueInstanceId('sma_21_close', existing)
      expect(unique).toBe('sma_21_close_2')
    })

    it('appends _3, _4, etc. for further duplicates', () => {
      const existing = new Set(['sma_21_close', 'sma_21_close_2'])
      const unique = ensureUniqueInstanceId('sma_21_close', existing)
      expect(unique).toBe('sma_21_close_3')
    })

    it('handles empty existing set', () => {
      const existing = new Set<string>()
      const unique = ensureUniqueInstanceId('sma_21_close', existing)
      expect(unique).toBe('sma_21_close')
    })
  })

  describe('generateDisplayName', () => {
    it('generates name for SMA with period', () => {
      const name = generateDisplayName('sma', 'Simple Moving Average', {
        period: 21,
        source: 'close',
      })
      expect(name).toBe('Simple Moving Average (21, close)')
    })

    it('generates name for EMA with period', () => {
      const name = generateDisplayName('ema', 'Exponential Moving Average', {
        period: 9,
        source: 'close',
      })
      expect(name).toBe('Exponential Moving Average (9, close)')
    })

    it('generates name for RSI with period only', () => {
      const name = generateDisplayName('rsi', 'Relative Strength Index', {
        period: 14,
      })
      expect(name).toBe('Relative Strength Index (14)')
    })

    it('generates name for MACD with three periods', () => {
      const name = generateDisplayName('macd', 'MACD', {
        fast_period: 12,
        slow_period: 26,
        signal_period: 9,
      })
      expect(name).toBe('MACD (12, 26, 9)')
    })

    it('generates name for Bollinger with period and std_dev', () => {
      const name = generateDisplayName('bollinger', 'Bollinger Bands', {
        period: 20,
        std_dev: 2,
      })
      expect(name).toBe('Bollinger Bands (20, 2)')
    })

    it('returns tool name for unknown tool', () => {
      const name = generateDisplayName('unknown', 'Unknown Tool', { param: 123 })
      expect(name).toBe('Unknown Tool')
    })

    it('skips missing parameters', () => {
      const name = generateDisplayName('sma', 'SMA', { period: 21 })
      expect(name).toBe('SMA (21)')
    })
  })
})
