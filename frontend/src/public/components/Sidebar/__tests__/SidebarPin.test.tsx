import React from 'react';
import { configureStore } from '@reduxjs/toolkit';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { Provider, useSelector } from 'react-redux';
import { Router } from 'react-router-dom';

import { ERoutes } from '../../../constants/routes';
import { enMessages } from '../../../lang/locales/en_US';
import { setMenuItems } from '../../../redux/menu/actions';
import { reducer as menuReducer } from '../../../redux/menu/reducer';
import type { IMenu } from '../../../redux/menu/types';
import { ESubscriptionPlan } from '../../../types/account';
import { history } from '../../../utils/history';
import { Sidebar } from '../Sidebar';

jest.unmock('react-redux');

function SidebarLayout() {
  const className = useSelector(({ menu }: { menu: IMenu }) => menu.containerClassnames);

  return (
    <div className={className} data-testid="layout">
      <button type="button">Outside sidebar</button>
      <Sidebar />
    </div>
  );
}

const renderSidebar = () => {
  const store = configureStore({
    reducer: {
      authUser: () => ({
        account: { name: 'Example Company', billingPlan: ESubscriptionPlan.Free, isSubscribed: false },
      }),
      menu: menuReducer,
      templates: () => ({ isTemplateOwner: false }),
    },
  });

  store.dispatch(setMenuItems([{ id: 'workflows', label: 'menu.workflows', to: ERoutes.Workflows }]));

  return render(
    <Provider store={store}>
      <IntlProvider locale="en" messages={enMessages}>
        <Router history={history}>
          <SidebarLayout />
        </Router>
      </IntlProvider>
    </Provider>,
  );
};

const resize = (width: number) => {
  window.innerWidth = width;
  fireEvent(window, new Event('resize'));
};

const pinButton = () => screen.getByRole('button', { name: 'Keep sidebar open' });
const workflowsLink = () => screen.getByRole('link', { name: 'Workflows' });
const layout = () => screen.getByTestId('layout');

beforeEach(() => {
  localStorage.clear();
  window.innerWidth = 1200;
  history.replace(ERoutes.Main);
});

it('keeps the sidebar open after pointer exit, outside clicks and navigation until unpinned', () => {
  jest.useFakeTimers();
  try {
    renderSidebar();
    const sidebar = workflowsLink().closest('.sidebar')!;

    expect(layout()).toHaveClass('main-hidden');
    fireEvent.mouseOver(sidebar);
    expect(layout()).not.toHaveClass('main-hidden');
    expect(pinButton()).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(pinButton());
    expect(pinButton()).toHaveAttribute('aria-pressed', 'true');
    expect(sidebar).toHaveAttribute('data-sidebar-pinned');
    fireEvent.mouseLeave(sidebar);
    fireEvent.click(screen.getByRole('button', { name: 'Outside sidebar' }));
    act(() => {
      jest.runOnlyPendingTimers();
    });
    fireEvent.click(workflowsLink());
    expect(history.location.pathname).toBe(ERoutes.Workflows);
    expect(layout()).not.toHaveClass('main-hidden');

    fireEvent.click(pinButton());
    expect(pinButton()).toHaveAttribute('aria-pressed', 'false');
    expect(sidebar).not.toHaveAttribute('data-sidebar-pinned');
    fireEvent.mouseLeave(sidebar);
    expect(layout()).toHaveClass('main-hidden');
  } finally {
    jest.useRealTimers();
  }
});

it('restores the saved desktop setting and keeps the mobile menu independent', () => {
  const { unmount } = renderSidebar();
  fireEvent.focus(workflowsLink());
  fireEvent.click(pinButton());
  unmount();

  renderSidebar();
  expect(pinButton()).toHaveAttribute('aria-pressed', 'true');
  expect(layout()).not.toHaveClass('main-hidden');

  resize(800);
  expect(screen.queryByRole('button', { name: 'Keep sidebar open' })).not.toBeInTheDocument();
  expect(layout()).toHaveClass('main-hidden');
  const mobileLogo = screen.getByRole('link', { name: 'Go to Dashboard' });
  fireEvent.click(mobileLogo);
  expect(layout()).not.toHaveClass('main-hidden');
  fireEvent.click(mobileLogo);
  expect(layout()).toHaveClass('main-hidden');

  resize(1200);
  expect(pinButton()).toHaveAttribute('aria-pressed', 'true');
  expect(layout()).not.toHaveClass('main-hidden');
});
