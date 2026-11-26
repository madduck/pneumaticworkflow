import axios from 'axios';
import type { Request, Response } from 'express';
import { ERoutes } from '../../../public/constants/routes';
import { setAuthCookie } from '../../utils/cookie';
import { startOIDC, finishOIDC } from '../oidcHandler';

jest.mock('axios');
jest.mock('../../utils/cookie');
jest.mock('../../utils/request', () => ({ serverApi: { getUrl: (path: string) => path } }));

const cookieName = '__Host-pneumatic-oidc';
const response = () =>
  ({ set: jest.fn(), cookie: jest.fn(), redirect: jest.fn(), clearCookie: jest.fn() }) as unknown as Response;

function callbackRequest(returnTo: string, query = { code: 'test-code', state: 'test-state' }) {
  const cookie = encodeURIComponent(JSON.stringify({ browserKey: 'test-browser-key', returnTo }));
  return { query, get: jest.fn(() => `${cookieName}=${cookie}`) } as unknown as Request;
}

afterEach(() => jest.resetAllMocks());

it('starts the flow with a secure browser cookie and redirects to the provider', async () => {
  const authUri = 'https://sso.example.org/authorize';
  (axios.post as jest.Mock).mockResolvedValue({ data: { auth_uri: authUri } });
  const res = response();
  await startOIDC({ query: { return_to: '/tasks/' }, get: jest.fn() } as unknown as Request, res);

  expect(axios.post).toHaveBeenCalledWith(
    '/auth/oidc/auth-uri',
    { browser_key: expect.any(String) },
    expect.any(Object),
  );
  expect(res.cookie).toHaveBeenCalledWith(
    cookieName,
    expect.stringContaining('"returnTo":"/tasks/"'),
    expect.objectContaining({ httpOnly: true, secure: true, sameSite: 'lax', path: '/' }),
  );
  expect(res.redirect).toHaveBeenCalledWith(authUri);
});

it('posts the callback to the backend and returns to the original local page', async () => {
  (axios.post as jest.Mock).mockResolvedValue({ data: { token: 'local-session' } });
  const req = callbackRequest('/tasks/?sort=name');
  const res = response();
  await finishOIDC(req, res);

  expect(res.clearCookie).toHaveBeenCalledWith(cookieName, expect.any(Object));
  expect(axios.post).toHaveBeenCalledWith(
    '/auth/oidc/token',
    { code: 'test-code', state: 'test-state', browser_key: 'test-browser-key' },
    expect.any(Object),
  );
  expect(setAuthCookie).toHaveBeenCalledWith(req, res, { token: 'local-session' }, true);
  expect(res.redirect).toHaveBeenCalledWith('/tasks/?sort=name');
});

it.each(['//outside.example.org/', '/a/..//outside.example.org/', '/%5Coutside.example.org', ERoutes.Login])(
  'does not redirect to an unsafe return destination: %s',
  async (returnTo) => {
    (axios.post as jest.Mock).mockResolvedValue({ data: { token: 'local-session' } });
    const res = response();
    await finishOIDC(callbackRequest(returnTo), res);

    expect(res.redirect).toHaveBeenCalledWith(ERoutes.Main);
  },
);

it('does not restart auto-login on a provider error', async () => {
  const res = response();
  const req = { query: { error: 'access_denied' }, get: jest.fn() } as unknown as Request;
  await finishOIDC(req, res);

  expect(res.redirect).toHaveBeenCalledWith(`${ERoutes.Login}?local=1&oidc_error=1`);
  expect(axios.post).not.toHaveBeenCalled();
  expect(setAuthCookie).not.toHaveBeenCalled();
});
