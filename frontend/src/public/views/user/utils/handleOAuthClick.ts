import type { MouseEvent } from 'react';
import type { IntlShape } from 'react-intl';

import { EOAuthType } from '../../../types/auth';
import { ERoutes } from '../../../constants/routes';
import { SSOProvider } from '../../../../server/types';
import { getOAuthUrl } from '../../../api/getGoogleAuthUrl';
import { NotificationManager } from '../../../components/UI/Notifications';
import { isValidUri } from '../../../utils/urls';

export function handleSSOClick(provider: string | undefined, formatMessage: IntlShape['formatMessage']) {
  if (provider === 'oidc') {
    return (event: MouseEvent) => {
      event.preventDefault();
      const returnTo = new URLSearchParams(window.location.search).get('redirectUrl');
      window.location.assign(`${ERoutes.OAuthOIDC}${returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : ''}`);
    };
  }
  return handleOAuthClick(provider === SSOProvider.Auth0 ? EOAuthType.SSOAuth0 : EOAuthType.SSOOkta, formatMessage);
}

export const handleOAuthClick =
  (type: EOAuthType, formatMessage: IntlShape['formatMessage']) => async (event: MouseEvent) => {
    event.preventDefault();

    const showServiceUnavailable = () => {
      NotificationManager.warning({
        message: formatMessage({ id: 'user.oauth-unavailable' }, { type }),
      });
    };

    try {
      const result = await getOAuthUrl(type);

      if (
        result &&
        typeof result === 'object' &&
        typeof result.redirectUri === 'string' &&
        isValidUri(result.redirectUri)
      ) {
        window.location.assign(result.redirectUri);
        return;
      }

      showServiceUnavailable();
    } catch {
      showServiceUnavailable();
    }
  };
