import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useInView } from '../hooks/useInView';

/**
 * Captures the IntersectionObserver options passed at construction and lets
 * a test fire the callback synchronously. Mirrors the surface area the hook
 * actually uses (`observe`, `disconnect`, callback fan-out).
 */
type Trigger = (isIntersecting: boolean) => void;
let trigger: Trigger | null = null;
let lastObserverOptions: IntersectionObserverInit | null = null;
let observerInstances = 0;
let disconnectCalls = 0;

function installMockObserver() {
  trigger = null;
  lastObserverOptions = null;
  observerInstances = 0;
  disconnectCalls = 0;
  class MockObserver {
    constructor(cb: IntersectionObserverCallback, opts?: IntersectionObserverInit) {
      observerInstances += 1;
      lastObserverOptions = opts ?? null;
      trigger = (isIntersecting: boolean) => {
        cb(
          [{ isIntersecting } as unknown as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      };
    }
    observe = vi.fn();
    disconnect = () => {
      disconnectCalls += 1;
    };
    unobserve = vi.fn();
    takeRecords = vi.fn(() => []);
  }
  vi.stubGlobal('IntersectionObserver', MockObserver);
}

function Probe({
  options,
}: {
  options?: { threshold?: number; rootMargin?: string };
}) {
  const { ref, shown } = useInView<HTMLDivElement>(options);
  return (
    <div ref={ref} data-testid="probe" data-shown={shown ? 'yes' : 'no'} />
  );
}

describe('useInView', () => {
  beforeEach(() => {
    installMockObserver();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    trigger = null;
  });

  it('starts with shown=false when IntersectionObserver is available', () => {
    const { getByTestId } = render(<Probe />);
    expect(getByTestId('probe').dataset.shown).toBe('no');
    expect(observerInstances).toBe(1);
  });

  it('flips shown=true once the element intersects, then disconnects', () => {
    const { getByTestId } = render(<Probe />);
    expect(getByTestId('probe').dataset.shown).toBe('no');
    act(() => trigger!(true));
    expect(getByTestId('probe').dataset.shown).toBe('yes');
    // disconnect is called at least once — once explicitly inside the
    // callback, and React's effect cleanup may also call it when the deps
    // change. The semantic guarantee is "no longer observing", which the
    // ≥1 count covers without being brittle to effect-order details.
    expect(disconnectCalls).toBeGreaterThanOrEqual(1);
  });

  it('stays hidden when intersection entries report isIntersecting=false', () => {
    const { getByTestId } = render(<Probe />);
    act(() => trigger!(false));
    expect(getByTestId('probe').dataset.shown).toBe('no');
    // Observer still attached — we did not disconnect on a non-intersection
    expect(disconnectCalls).toBe(0);
  });

  it('forwards threshold and rootMargin options to the observer', () => {
    render(<Probe options={{ threshold: 0.42, rootMargin: '10px 0px' }} />);
    expect(lastObserverOptions?.threshold).toBe(0.42);
    expect(lastObserverOptions?.rootMargin).toBe('10px 0px');
  });

  it('applies sensible defaults when no options are passed', () => {
    render(<Probe />);
    expect(lastObserverOptions?.threshold).toBe(0.15);
    expect(lastObserverOptions?.rootMargin).toBe('0px 0px -40px 0px');
  });

  it('initializes shown=true when IntersectionObserver is missing', () => {
    // Simulate older environment by removing the global. The hook should
    // bail out of observation entirely and render content as visible.
    vi.stubGlobal('IntersectionObserver', undefined);
    const { getByTestId } = render(<Probe />);
    expect(getByTestId('probe').dataset.shown).toBe('yes');
  });
});
