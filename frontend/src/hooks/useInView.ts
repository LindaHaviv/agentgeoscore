import { useEffect, useRef, useState } from 'react';

/**
 * Reveal-on-scroll hook. Returns a ref to attach and a `shown` flag that
 * flips true the first time the element crosses the viewport threshold.
 * Once revealed it stays revealed — we never re-hide on scroll-out.
 *
 * If IntersectionObserver is unavailable (older test env, JSDOM without
 * polyfill), `shown` initializes to true so content is visible.
 */
export function useInView<T extends Element>(options?: {
  threshold?: number;
  rootMargin?: string;
}) {
  const ref = useRef<T | null>(null);
  const [shown, setShown] = useState<boolean>(
    typeof window === 'undefined' || typeof IntersectionObserver === 'undefined'
  );

  useEffect(() => {
    if (shown) return;
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShown(true);
            observer.disconnect();
            break;
          }
        }
      },
      {
        threshold: options?.threshold ?? 0.15,
        rootMargin: options?.rootMargin ?? '0px 0px -40px 0px',
      }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [shown, options?.threshold, options?.rootMargin]);

  return { ref, shown };
}
