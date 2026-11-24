import React from 'react';
import { configureStore } from '@reduxjs/toolkit';
import { render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { Router } from 'react-router-dom';

import { reducer as menuReducer } from '../../../redux/menu/reducer';
import { ESubscriptionPlan } from '../../../types/account';
import { history } from '../../../utils/history';
import { Sidebar } from '../Sidebar';

jest.unmock('react-redux');

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

  return render(
    <Provider store={store}>
      <Router history={history}>
        <Sidebar />
      </Router>
    </Provider>,
  );
};

it('shows the company name next to the logo instead of the plan ribbon', () => {
  renderSidebar();

  const dashboardLink = screen.getByRole('link', { name: 'Dashboard' });
  expect(dashboardLink.nextElementSibling).toHaveTextContent('Example Company');
  expect(screen.queryByText('Free Plan')).not.toBeInTheDocument();
});
