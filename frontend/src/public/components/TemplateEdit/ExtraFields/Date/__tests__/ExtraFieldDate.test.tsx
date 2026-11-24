import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { enUS } from 'date-fns/locale';

import { ExtraFieldDate } from '../ExtraFieldDate';
import { FieldLabel } from '../../utils/FieldLabel';
import { IWorkflowExtraFieldProps } from '../../types';
import { intlMock } from '../../../../../__stubs__/intlMock';
import { makeExtraField } from '../../../../../__stubs__/fields.factory';
import { EExtraFieldMode, EExtraFieldType } from '../../../../../types/template';
import { EFieldLabelPosition } from '../../../../../types/fieldset';
import { enMessages } from '../../../../../lang/locales/en_US';

jest.mock('../../utils/FieldLabel', () => ({
  FieldLabel: jest.fn(() => null),
}));

jest.mock('../../utils/FieldWithName', () => {
  const React = require('react');
  return {
    FieldWithName: jest.fn(() => React.createElement('div', { 'data-testid': 'field-with-name' })),
  };
});

jest.mock('../../../../icons', () => ({
  DateIcon: () => null,
  RoundClearIconLg: () => null,
}));

jest.mock('../../utils/getFieldValidator', () => ({
  getFieldValidator: jest.fn(() => jest.fn(() => '')),
}));

jest.mock('../../utils/getInputNameBackground', () => ({
  getInputNameBackground: jest.fn(() => ''),
}));

jest.mock('../../../../../hooks/useDatePickerSettings', () => ({
  useDatePickerSettings: () => ({ locale: enUS, timezone: 'Pacific/Kiritimati', dateFdw: 0 }),
}));

const wrapper = ({ children }: React.PropsWithChildren<{}>) => (
  <IntlProvider locale="en" messages={enMessages}>
    {children}
  </IntlProvider>
);

describe('ExtraFieldDate', () => {
  const mockEditField = jest.fn();

  const baseProps: IWorkflowExtraFieldProps = {
    field: makeExtraField({ name: 'Due Date', type: EExtraFieldType.Date }),
    intl: intlMock,
    editField: mockEditField,
    mode: EExtraFieldMode.ProcessRun,
    isDisabled: false,
    accountId: 1,
    labelPosition: EFieldLabelPosition.Top,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows and edits the saved time in the browser timezone', async () => {
    const saved = new Date(2024, 6, 15, 8, 7).getTime() / 1000;
    const field = { ...baseProps.field, value: String(saved) };
    const { rerender } = render(<ExtraFieldDate {...baseProps} field={field} />, { wrapper });
    const input = screen.getByRole('textbox', { name: 'Due Date' });
    expect(input).toHaveValue('Jul 15, 2024, 08:07');

    fireEvent.click(input);
    const timeInput = await waitFor(() => {
      const element = document.querySelector('input[type="time"]');
      expect(element).toHaveValue('08:07');
      return element!;
    });
    fireEvent.change(timeInput, { target: { value: '23:17' } });

    const edited = new Date(2024, 6, 15, 23, 17).getTime() / 1000;
    expect(mockEditField).toHaveBeenLastCalledWith({ value: edited });
    rerender(<ExtraFieldDate {...baseProps} field={{ ...field, value: edited }} />);
    expect(input).toHaveValue('Jul 15, 2024, 23:17');
  });

  it('keeps the time control open after selecting a day in an empty field', async () => {
    // The form reflects edits back into the field, as the runtime form does.
    const Form = () => {
      const [field, setField] = React.useState(baseProps.field);
      return (
        <ExtraFieldDate {...baseProps} field={field} editField={(updates) => setField({ ...field, ...updates })} />
      );
    };
    render(<Form />, { wrapper });
    fireEvent.click(screen.getByRole('textbox', { name: 'Due Date' }));
    fireEvent.click(
      screen.getByText('15', { selector: '.react-datepicker__day:not(.react-datepicker__day--outside-month)' }),
    );

    await waitFor(() => expect(document.querySelector('input[type="time"]')).toHaveValue('00:00'));
  });

  it('clears an existing value and disables edits in a disabled field', () => {
    const field = { ...baseProps.field, value: '1718409600' };
    const { rerender } = render(<ExtraFieldDate {...baseProps} field={field} />, { wrapper });

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(mockEditField).toHaveBeenLastCalledWith({ value: '' });

    rerender(<ExtraFieldDate {...baseProps} field={field} isDisabled />);
    expect(screen.getByRole('textbox', { name: 'Due Date' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();
  });

  describe('label-left support', () => {
    it('ProcessRun + labelPosition=Left: passes labelPosition=Left to FieldLabel', () => {
      render(<ExtraFieldDate {...baseProps} labelPosition={EFieldLabelPosition.Left} />, { wrapper });

      const fieldLabelMock = FieldLabel as jest.Mock;
      expect(fieldLabelMock).toHaveBeenCalledTimes(1);
      expect(fieldLabelMock).toHaveBeenCalledWith(
        expect.objectContaining({
          labelPosition: EFieldLabelPosition.Left,
        }),
        {},
      );
    });

    it('ProcessRun + labelPosition=Top: renders static name div, no FieldLabel', () => {
      render(<ExtraFieldDate {...baseProps} labelPosition={EFieldLabelPosition.Top} />, { wrapper });

      const fieldLabelMock = FieldLabel as jest.Mock;
      expect(fieldLabelMock).not.toHaveBeenCalled();
      expect(screen.getByText('Due Date')).toBeInTheDocument();
    });
  });
});
