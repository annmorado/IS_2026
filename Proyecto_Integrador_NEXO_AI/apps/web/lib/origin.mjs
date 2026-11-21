/**
 * Validate the Origin for cookie-authenticated POST/DELETE endpoints (CSRF).
 * Next.js can normalize request.url to localhost during local development even
 * when the browser used 127.0.0.1. We accept that difference ONLY for loopback
 * addresses, matching the browser's Origin to its actual Host header and port.
 * No arbitrary external Origin, wildcard, or missing Origin is allowed.
 */
const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]']);

export function allowedOrigin(request) {
  const originHeader = request.headers.get('origin');
  const hostHeader = request.headers.get('host');
  if (!originHeader || !hostHeader) return false;

  try {
    const origin = new URL(originHeader);
    const requestUrl = new URL(request.url);

    // An Origin header must be exactly an origin: no credentials, path, or query.
    if (origin.origin !== originHeader) return false;
    if (!['http:', 'https:'].includes(origin.protocol)) return false;

    // The Origin must match the public Host actually requested by the browser.
    if (origin.host.toLowerCase() !== hostHeader.toLowerCase()) return false;

    // Normal same-origin request.
    if (origin.origin === requestUrl.origin) return true;

    // Next.js local normalization: 127.0.0.1 <-> localhost (and IPv6 loopback).
    // Never apply this exception to non-loopback networks or different ports.
    return origin.protocol === 'http:'
      && requestUrl.protocol === 'http:'
      && origin.port === requestUrl.port
      && LOOPBACK.has(origin.hostname.toLowerCase())
      && LOOPBACK.has(requestUrl.hostname.toLowerCase());
  } catch {
    return false;
  }
}
