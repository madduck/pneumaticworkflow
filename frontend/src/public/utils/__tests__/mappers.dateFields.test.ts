import { EExtraFieldMode, EExtraFieldType } from '../../types/template';
import { hasFieldError } from '../../components/TemplateEdit/ExtraFields/utils/getFieldValidator';
import { makeExtraField } from '../../__stubs__/fields.factory';
import { makeFieldsetRuntime } from '../../__stubs__/fieldsets.factory';
import { formatTaskDatesForRedux, getNormalizedKickoff, mapOutputToCompleteTask } from '../mappers';

describe('workflow date and time field payloads', () => {
  const timestamp = Date.parse('2024-07-16T03:17:00Z') / 1000;
  const dateField = (value: number | string) =>
    makeExtraField({ apiName: 'appointment', type: EExtraFieldType.Date, value });

  it.each([timestamp, String(timestamp), 0])('sends kickoff field %p as an exact UTC timestamp', (value) => {
    expect(getNormalizedKickoff({ fields: [dateField(value)] })).toEqual({ appointment: Number(value) });
  });

  it.each([timestamp, String(timestamp), 0])('sends task output %p as an exact UTC timestamp', (value) => {
    expect(mapOutputToCompleteTask([dateField(value)])[0].value).toBe(Number(value));
  });

  it('accepts timestamp zero in a required date field', () => {
    expect(hasFieldError({ ...dateField(0), isRequired: true }, EExtraFieldMode.ProcessRun)).toBe(false);
  });

  it('leaves cleared date fields empty', () => {
    const field = dateField('');
    expect(getNormalizedKickoff({ fields: [field] })).toEqual({ appointment: null });
    expect(mapOutputToCompleteTask([field])[0].value).toBeNull();
  });

  it('keeps the exact server values in task outputs and fieldsets after loading', () => {
    const field = dateField(String(timestamp));
    const task = formatTaskDatesForRedux({
      dueDateTsp: timestamp,
      output: [field],
      fieldsets: [makeFieldsetRuntime({ fields: [field] })],
    });

    expect(task.output[0].value).toBe(String(timestamp));
    expect(task.fieldsets[0].fields[0].value).toBe(String(timestamp));
    expect(task.dueDate).toBe('2024-07-16T03:17:00Z');
  });
});
