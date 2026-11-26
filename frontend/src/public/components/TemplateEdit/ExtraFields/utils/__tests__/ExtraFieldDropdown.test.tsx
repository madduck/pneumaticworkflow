import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';

import { ExtraFieldDropdown } from '../ExtraFieldDropdown';
import { Dropdown } from '../../../../UI';
import { enMessages } from '../../../../../lang/locales/en_US';

jest.mock('../../../../UI', () => {
  const actual = jest.requireActual('../../../../UI');
  return {
    ...actual,
    Dropdown: jest.fn(actual.Dropdown),
  };
});

jest.mock('../../../../UI/OutsideClickHandler', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const baseProps = {
  isRequired: false,
  isRequiredDisabled: false,
  isHidden: false,
  onEditField: jest.fn(),
  onDeleteField: jest.fn(),
  onMoveFieldUp: jest.fn(),
  onMoveFieldDown: jest.fn(),
  showDatasetOption: false,
  datasetOptions: [],
  onDatasetSelect: jest.fn(),
};

const renderWithIntl = (ui: React.ReactElement) =>
  render(
    <IntlProvider locale="en" messages={enMessages}>
      {ui}
    </IntlProvider>,
  );

describe('ExtraFieldDropdown', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const getRequiredSwitch = () => screen.getByRole('switch', { name: 'Required', hidden: true });
  const getHiddenSwitch = () => screen.getByRole('switch', { name: 'Hidden', hidden: true });

  describe('Render', () => {
    it('renders Hidden switch', () => {
      renderWithIntl(<ExtraFieldDropdown {...baseProps} isHidden={false} />);

      expect(getHiddenSwitch()).toBeInTheDocument();
    });
  });

  describe('Default value', () => {
    it('shows an empty editor for a field without a default', () => {
      renderWithIntl(<ExtraFieldDropdown {...baseProps} />);

      userEvent.click(screen.getByRole('button', { name: 'Field options' }));
      expect(screen.getByRole('textbox', { name: 'Default value' })).toHaveValue('');
    });

    it('shows, clears and edits a saved multiline default in the menu', async () => {
      const onEditField = jest.fn();
      const FieldMenu = () => {
        const [defaultValue, setDefaultValue] = React.useState('First line\nSecond line');
        return (
          <ExtraFieldDropdown
            {...baseProps}
            defaultValue={defaultValue}
            onEditField={(changes) => {
              onEditField(changes);
              setDefaultValue(changes.default ?? '');
            }}
          />
        );
      };
      renderWithIntl(<FieldMenu />);

      const toggle = screen.getByRole('button', { name: 'Field options' });
      userEvent.click(toggle);
      const input = screen.getByRole('textbox', { name: 'Default value' });
      expect(input).toHaveValue('First line\nSecond line');

      await waitFor(() => expect(screen.getByRole('menu')).not.toHaveStyle({ pointerEvents: 'none' }));
      userEvent.clear(input);
      expect(onEditField).toHaveBeenLastCalledWith({ default: '' });

      userEvent.type(input, 'New value{enter}Next line');
      expect(onEditField).toHaveBeenLastCalledWith({ default: 'New value\nNext line' });
      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      expect(input).toHaveValue('New value\nNext line');
    });
  });

  describe('Required / Hidden mutual exclusion', () => {
    it('Required switch is disabled when field is hidden', () => {
      renderWithIntl(<ExtraFieldDropdown {...baseProps} isHidden={true} />);

      expect(getRequiredSwitch()).toBeDisabled();
    });

    it('Hidden switch is disabled when field is required', () => {
      renderWithIntl(<ExtraFieldDropdown {...baseProps} isRequired={true} />);

      expect(getHiddenSwitch()).toBeDisabled();
    });

    it('Required switch is disabled when isRequiredDisabled', () => {
      renderWithIntl(<ExtraFieldDropdown {...baseProps} isRequiredDisabled={true} />);

      expect(getRequiredSwitch()).toBeDisabled();
    });
  });

  describe('Callbacks', () => {
    it('toggling Hidden on calls onEditField with isHidden=true', () => {
      const onEditField = jest.fn();
      renderWithIntl(<ExtraFieldDropdown {...baseProps} isHidden={false} onEditField={onEditField} />);

      userEvent.click(getHiddenSwitch());

      expect(onEditField).toHaveBeenCalledTimes(1);
      expect(onEditField).toHaveBeenCalledWith({ isHidden: true });
    });

    it('toggling Hidden off calls onEditField with isHidden=false', () => {
      const onEditField = jest.fn();
      renderWithIntl(<ExtraFieldDropdown {...baseProps} isHidden={true} onEditField={onEditField} />);

      userEvent.click(getHiddenSwitch());

      expect(onEditField).toHaveBeenCalledTimes(1);
      expect(onEditField).toHaveBeenCalledWith({ isHidden: false });
    });
  });

  describe('Dataset option for list field types', () => {
    const onDatasetSelect = jest.fn();
    const datasetProps = {
      ...baseProps,
      showDatasetOption: true,
      datasetOptions: [
        { label: 'Dataset A', value: '1' },
        { label: 'Dataset B', value: '2' },
      ],
      onDatasetSelect,
    };

    it('calls onDatasetSelect with dataset id when dataset option is clicked', () => {
      renderWithIntl(<ExtraFieldDropdown {...datasetProps} />);

      userEvent.click(screen.getByText('Dataset A'));

      expect(onDatasetSelect).toHaveBeenCalledWith(1);
    });
    it('renders dataset sub-options when datasetOptions is provided', () => {
      renderWithIntl(<ExtraFieldDropdown {...datasetProps} />);

      expect(screen.getByText('Dataset A')).toBeInTheDocument();
      expect(screen.getByText('Dataset B')).toBeInTheDocument();
    });

    it('passes dataset subOptions to Dropdown when datasetOptions is provided', () => {
      (Dropdown as jest.Mock).mockClear();

      renderWithIntl(<ExtraFieldDropdown {...datasetProps} />);

      const dropdownProps = (Dropdown as jest.Mock).mock.calls[0]?.[0];
      const datasetMenuItem = dropdownProps.options.find(
        (opt: any) => opt.className && opt.className.includes('dataset-submenu'),
      );
      expect(datasetMenuItem.subOptions).toBeDefined();
      expect(datasetMenuItem.subOptions.length).toBeGreaterThan(0);
    });
  });
});
