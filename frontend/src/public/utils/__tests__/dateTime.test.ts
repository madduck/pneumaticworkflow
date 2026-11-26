import {
  DELAY_TITLE_TEMPLATE,
  formatDelayRequest,
  formatDuration,
  getSeconds,
  parseDuration,
  parseUnixSeconds,
  formatWorkflowFieldDateTime,
  fromUnixSeconds,
} from '../dateTime';

describe('dateTime', () => {
  const mockDuration = '12 05:30:00';
  const mockDurationWithoutDays = '00 00:12:00';
  const mockSplittedDuration = { days: 12, hours: 5, minutes: 120 };

  describe('parseDuration', () => {
    it('Parses duration from the back end correctly', () => {
      const result = parseDuration(mockDuration);
      const expected = { days: 12, hours: 5, minutes: 30 };

      expect(result).toEqual(expected);
    });
  });

  describe('getSeconds', () => {
    it('Returns correct seconds count', () => {
      const result = getSeconds(mockSplittedDuration);
      const expected = 1062000;

      expect(result).toEqual(expected);
    });
  });

  describe('formatDuration', () => {
    it('Formats duration correctly #1', () => {
      const result = formatDuration(mockDuration, DELAY_TITLE_TEMPLATE);
      const expected = '12d 5h 30m';

      expect(result).toEqual(expected);
    });
  });

  describe('formatDuration', () => {
    it('Formats duration correctly #2', () => {
      const result = formatDuration(mockDurationWithoutDays, DELAY_TITLE_TEMPLATE);
      const expected = '12m';

      expect(result).toEqual(expected);
    });
  });

  describe('formatDelayRequest', () => {
    it('Formats duration for the request correctly', () => {
      const result = formatDelayRequest(mockSplittedDuration);
      const expected = '12 07:00:00';

      expect(result).toEqual(expected);
    });
  });

  describe('parseUnixSeconds', () => {
    it('returns finite numbers as unix seconds', () => {
      expect(parseUnixSeconds(1718409600)).toBe(1718409600);
    });

    it('parses numeric strings', () => {
      expect(parseUnixSeconds('1718409600')).toBe(1718409600);
    });

    it('returns null for formatted dates and empty values', () => {
      expect(parseUnixSeconds('Jun 15, 2024')).toBeNull();
      expect(parseUnixSeconds('')).toBeNull();
      expect(parseUnixSeconds(null)).toBeNull();
    });
  });

  describe('workflow date and time fields', () => {
    const timestamp = new Date(2024, 6, 15, 23, 17).getTime() / 1000;

    it.each([timestamp, String(timestamp)])('displays %p using the browser date and time', (value) => {
      expect(formatWorkflowFieldDateTime(value)).toBe('Jul 15, 2024, 23:17');
    });

    it.each(['-1', 0, '1718409600.5'])('reads the exact stored instant %p', (value) => {
      expect(fromUnixSeconds(value)?.getTime()).toBe(Number(value) * 1000);
    });

    it.each(['', 'not-a-date', null])('returns null for empty and invalid values: %p', (value) => {
      expect(formatWorkflowFieldDateTime(value)).toBeNull();
    });
  });
});
