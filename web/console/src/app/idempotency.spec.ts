import { newIdempotencyKey } from './idempotency';

describe('newIdempotencyKey', () => {
  it('makes version 4 UUIDs that do not repeat', () => {
    const keys = new Set(Array.from({ length: 1000 }, newIdempotencyKey));

    expect(keys.size).toBe(1000);
    for (const key of keys) {
      expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    }
  });
});
