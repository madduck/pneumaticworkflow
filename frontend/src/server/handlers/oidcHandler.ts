import { randomBytes } from 'node:crypto';
import { isIP } from 'node:net';
import axios from 'axios';
import type { Request, Response } from 'express';
import { ERoutes } from '../../public/constants/routes';
import { parseCookies } from '../../public/utils/cookie';
import { setAuthCookie } from '../utils/cookie';
import { serverApi } from '../utils';

const COOKIE = '__Host-pneumatic-oidc';
const COOKIE_OPTIONS = { secure: true, httpOnly: true, sameSite: 'lax', path: '/' } as const;
const FAILURE_URL = `${ERoutes.Login}?local=1&oidc_error=1`;
const SAFE_ORIGIN = 'https://example.org';

export function isOIDCEnabled() {
  return process.env.SSO_AUTH === 'yes' && process.env.SSO_PROVIDER === 'oidc';
}

function safeReturnPath(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.length > 1500) return ERoutes.Main;
  try {
    const decoded = decodeURIComponent(value.split('?')[0]);
    if (decoded.startsWith('//') || /[\\\s]/.test(decoded)) return ERoutes.Main;
    const url = new URL(value, SAFE_ORIGIN);
    if (url.origin !== SAFE_ORIGIN || url.pathname.startsWith('//') || /^\/(auth|oauth)(?:\/|$)/.test(url.pathname)) {
      return ERoutes.Main;
    }
    return url.pathname + url.search;
  } catch {
    return ERoutes.Main;
  }
}

function noStore(res: Response) {
  res.set({ 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' });
}

function post<T>(req: Request, path: string, data: Record<string, string>) {
  const realIp = req.get('X-Real-IP');
  return axios.post<T>(serverApi.getUrl(path), data, {
    timeout: 22000,
    maxRedirects: 0,
    headers: { 'User-Agent': req.get('user-agent'), 'X-Forwarded-For': realIp && isIP(realIp) ? realIp : req.ip },
  });
}

export async function startOIDC(req: Request, res: Response) {
  noStore(res);
  const browserKey = randomBytes(32).toString('base64url');
  const returnTo = safeReturnPath(req.query.return_to);
  try {
    const { data } = await post<{ auth_uri: string }>(req, '/auth/oidc/auth-uri', { browser_key: browserKey });
    const uri = new URL(data.auth_uri);
    if (uri.protocol !== 'https:') return res.redirect(FAILURE_URL);
    res.cookie(COOKIE, JSON.stringify({ browserKey, returnTo }), { ...COOKIE_OPTIONS, maxAge: 600000 });
    return res.redirect(uri.toString());
  } catch {
    return res.redirect(FAILURE_URL);
  }
}

export async function finishOIDC(req: Request, res: Response) {
  noStore(res);
  res.clearCookie(COOKIE, COOKIE_OPTIONS);
  const { code, state, error } = req.query;
  try {
    const cookie = parseCookies(req.get('cookie'))[COOKIE];
    if (error || typeof code !== 'string' || typeof state !== 'string' || !cookie) {
      return res.redirect(FAILURE_URL);
    }
    const { browserKey, returnTo } = JSON.parse(cookie);
    if (typeof browserKey !== 'string') return res.redirect(FAILURE_URL);
    const { data } = await post<{ token: string }>(req, '/auth/oidc/token', { code, state, browser_key: browserKey });
    if (typeof data.token !== 'string' || !data.token) return res.redirect(FAILURE_URL);
    setAuthCookie(req, res, data, true);
    return res.redirect(safeReturnPath(returnTo));
  } catch {
    return res.redirect(FAILURE_URL);
  }
}
