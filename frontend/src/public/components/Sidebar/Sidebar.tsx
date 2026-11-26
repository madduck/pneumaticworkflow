import React, { useCallback } from 'react';
import classnames from 'classnames';
import { useIntl } from 'react-intl';
import { useDispatch, useSelector } from 'react-redux';

import { ERoutes } from '../../constants/routes';
import { openSelectTemplateModal } from '../../redux/actions';
import { getSidebarState } from '../../redux/selectors/sidebar';
import { EPlanActions } from '../../utils/getPlanPendingActions';
import { NavLink } from '../NavLink';
import { LogoContainer } from '../Logo';
import { checkHasTopBar } from '../TopNav/utils/checkHasTopBar';

import { SidebarMenu } from './SidebarMenu';
import { useSidebarNavigation } from './useSidebarNavigation';
import styles from './Sidebar.css';

export function Sidebar() {
  const dispatch = useDispatch();
  const { formatMessage } = useIntl();
  const {
    authUser: {
      account: { isBlocked, billingPlan: plan, name: companyName },
      isSupermode,
    },
    containerClassnames,
    menuHiddenBreakpoint,
    menuItems,
    pendingActions,
  } = useSelector(getSidebarState);
  const {
    activeItemId,
    closeMenu,
    handleCloseMenu,
    handleMobileMenuToggle,
    handleOpenMenu,
    handleTogglePin,
    isMobile,
    isPinnedOpen,
  } = useSidebarNavigation({ containerClassnames, menuHiddenBreakpoint, menuItems });
  const pinLabel = formatMessage({ id: 'sidebar.keep-open' });
  const extraSpace = checkHasTopBar(Boolean(isBlocked), plan, Boolean(isSupermode));
  const handleRunWorkflow = useCallback(() => {
    if (!pendingActions.includes(EPlanActions.ChoosePlan)) {
      dispatch(openSelectTemplateModal());
    }
  }, [dispatch, pendingActions]);

  return (
    <div
      className="no-print sidebar"
      onMouseOver={handleOpenMenu}
      onFocus={handleOpenMenu}
      onBlur={(event) => {
        if (!isMobile && !event.currentTarget.contains(event.relatedTarget)) {
          handleCloseMenu();
        }
      }}
      onMouseLeave={handleCloseMenu}
      data-sidebar-pinned={isPinnedOpen || undefined}
    >
      <NavLink
        aria-label="Go to Dashboard"
        to={ERoutes.Main}
        onClick={handleMobileMenuToggle}
        className={classnames(styles['logo-mobile'], extraSpace && styles['logo__extra-space'])}
      >
        <LogoContainer className={classnames('active', styles['logo'])} size="sm" theme="light" />
      </NavLink>
      <div className={classnames('main-menu', styles['sidebar_menu'], extraSpace && styles['menu__extra-space'])}>
        <div className={styles['sidebar-header']}>
          <NavLink
            aria-label={formatMessage({ id: 'menu.dashboard' })}
            to={ERoutes.Main}
            className={styles['logo-desktop']}
          >
            <LogoContainer size="md" className="active" theme="light" />
          </NavLink>
          <span className={styles['company-name']} title={companyName}>
            {companyName}
          </span>
        </div>
        <SidebarMenu
          activeItemId={activeItemId}
          containerClassnames={containerClassnames}
          isMobile={isMobile}
          menuItems={menuItems}
          onCloseMenu={closeMenu}
          onRunWorkflow={handleRunWorkflow}
          plan={plan}
        />
        {!isMobile && (
          <button
            type="button"
            className={styles['pin-button']}
            aria-label={pinLabel}
            aria-pressed={isPinnedOpen}
            title={pinLabel}
            onClick={handleTogglePin}
          >
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24">
              <path
                d="M12 17v5m-7-5h14v-2a2 2 0 0 0-1-1.73l-1.06-.61A2 2 0 0 1 16 11V6l2-2V2H6v2l2 2v5a2 2 0 0 1-.94 1.66L6 13.27A2 2 0 0 0 5 15z"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
