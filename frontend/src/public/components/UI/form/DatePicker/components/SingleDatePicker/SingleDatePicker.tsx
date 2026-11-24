import React, { useRef } from 'react';
import DatePicker from 'react-datepicker';
import { useIntl } from 'react-intl';

import { useDatePickerSettings } from '../../../../../../hooks/useDatePickerSettings';
import { WORKFLOW_FIELD_DATE_TIME_FORMAT } from '../../../../../../utils/dateTime';
import { CustomInput } from '../CustomInput/CustomInput';
import type { ISingleDatePickerProps } from '../../types';
import {
  formatDatePickerDisplayValue,
  normalizeDatePickerDate,
  toCalendarDate,
} from '../../utils/normalizeDatePickerDate';

import styles from '../../DatePicker.modules.css';

export const SingleDatePicker = ({
  selected,
  onChange,
  startDay,
  ariaLabel,
  withTime = false,
  isClearable = true,
  selectsRange: _selectsRange,
  ...props
}: ISingleDatePickerProps) => {
  const { formatMessage } = useIntl();
  const { locale, timezone, dateFdw } = useDatePickerSettings();
  const datePickerRef = useRef<DatePicker>(null);
  const selectedDate = withTime ? selected : toCalendarDate(selected, timezone);
  const clearLabel = formatMessage({ id: 'ui-input.clear' });

  const handleChangeDate = (date: Date | null) => {
    if (withTime) {
      onChange(date);
      return;
    }

    datePickerRef.current?.setOpen(false);

    onChange(
      normalizeDatePickerDate({
        date,
        timezone,
        mode: 'start',
        startDay: Boolean(startDay),
      }),
    );
  };

  return (
    <div className={styles['date-picker']}>
      <DatePicker
        {...props}
        ref={datePickerRef}
        ariaLabelClose={clearLabel}
        clearButtonTitle={clearLabel}
        customInput={<CustomInput aria-label={ariaLabel} />}
        isClearable={Boolean(isClearable && selected)}
        shouldCloseOnSelect={!withTime}
        showTimeInput={withTime}
        timeInputLabel={withTime ? formatMessage({ id: 'ui-date-picker.local-time' }) : undefined}
        dateFormat={withTime ? WORKFLOW_FIELD_DATE_TIME_FORMAT : props.dateFormat}
        locale={locale}
        selected={selectedDate}
        value={withTime ? undefined : selected ? formatDatePickerDisplayValue(selected, timezone) : ''}
        calendarStartDay={dateFdw}
        onChange={handleChangeDate}
      />
    </div>
  );
};
