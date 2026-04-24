import { describe, expect, it } from 'vitest';
import { normalizeDomain } from '../api';

describe('normalizeDomain', () => {
  it('strips scheme', () => {
    expect(normalizeDomain('https://Example.com')).toBe('example.com');
    expect(normalizeDomain('http://example.com')).toBe('example.com');
  });
  it('strips path and query', () => {
    expect(normalizeDomain('example.com/foo?bar=1')).toBe('example.com');
  });
  it('trims whitespace', () => {
    expect(normalizeDomain('  example.com  ')).toBe('example.com');
  });
});
