import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';

import { SingleDatePicker } from '../components/SingleDatePicker/SingleDatePicker';
import { enMessages } from '../../../../../lang/locales/en_US';
import { ELocale } from '../../../../../types/locale';

jest.mock('react-redux', () => ({
  useSelector: (selector: (state: unknown) => unknown) =>
    selector({
      authUser: {
        timezone: 'UTC',
        language: ELocale.English,
        dateFdw: 0,
      },
    }),
}));

const renderSingleDatePicker = (props: Partial<React.ComponentProps<typeof SingleDatePicker>> = {}) => {
  const defaultProps: React.ComponentProps<typeof SingleDatePicker> = {
    selected: new Date('2024-06-15T00:00:00.000Z'),
    onChange: jest.fn(),
    startDay: true,
    ...props,
  };

  return render(
    <IntlProvider locale="en" messages={enMessages as unknown as Record<string, string>}>
      <SingleDatePicker {...defaultProps} />
    </IntlProvider>,
  );
};

describe('SingleDatePicker', () => {
  it('clears the selected date via clear button', async () => {
    const onChange = jest.fn();

    renderSingleDatePicker({ onChange });

    const clearButton = screen.getByLabelText(/clear/i);
    userEvent.click(clearButton);

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(null);
    });
  });

  it('uses the default local time when the user picks the first day', () => {
    const onChange = jest.fn();
    renderSingleDatePicker({
      withTime: true,
      defaultTime: { hours: 17, minutes: 30 },
      selected: null,
      openToDate: new Date(2024, 6, 15),
      onChange,
    });
    const input = screen.getByRole('textbox');
    expect(input).toHaveValue('');
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.click(input);
    fireEvent.click(screen.getByText('15', { selector: '.react-datepicker__day' }));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(new Date(2024, 6, 15, 17, 30));
  });

  it('lets the user enter a different time before picking a day', () => {
    const onChange = jest.fn();
    const { container } = renderSingleDatePicker({
      withTime: true,
      defaultTime: { hours: 17, minutes: 30 },
      selected: null,
      openToDate: new Date(2024, 6, 15),
      onChange,
    });
    fireEvent.click(screen.getByRole('textbox'));
    const timeInput = container.querySelector('input[type="time"]')!;
    fireEvent.change(timeInput, { target: { value: '00:00' } });

    expect(onChange).toHaveBeenCalledWith(new Date(2024, 6, 15, 0, 0));
  });

  it('does not render built-in clear button when isClearable is false', () => {
    renderSingleDatePicker({ isClearable: false });

    expect(screen.queryByLabelText(/clear/i)).not.toBeInTheDocument();
  });

  it('does not render clear button when there is no selected date', () => {
    renderSingleDatePicker({ selected: null });

    expect(screen.queryByLabelText(/clear/i)).not.toBeInTheDocument();
  });
});
