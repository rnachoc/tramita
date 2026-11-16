import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { ApiError, CoreApi } from '../api/core-api';
import { ClaimSummary } from '../api/models';
import { Inbox } from './inbox';

const claim = (id: string, incident: string): ClaimSummary => ({
  claim_id: id,
  policy_number: 'BR-HP-000001',
  claim_type: 'HOME_WATER',
  incident_date: incident,
  reported_date: incident,
  status: 'PENDING_REVIEW',
  updated_at: incident,
});

async function render(api: Partial<CoreApi>): Promise<HTMLElement> {
  TestBed.configureTestingModule({
    imports: [Inbox],
    providers: [provideRouter([]), { provide: CoreApi, useValue: api }],
  });
  const fixture = TestBed.createComponent(Inbox);
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
}

describe('Inbox', () => {
  it('lists the claims oldest incident first, with Spanish labels and links', async () => {
    const page = await render({
      claims: () => of([claim('CL-2', '2026-03-02'), claim('CL-1', '2026-01-05')]),
    });

    const rows = [...page.querySelectorAll('tbody tr')].map((r) => r.textContent ?? '');
    expect(rows[0]).toContain('CL-1');
    expect(rows[0]).toContain('Daños por agua');
    expect(rows[0]).toContain('Pendiente de revisión');
    expect(page.querySelector('tbody a')?.getAttribute('href')).toBe('/claims/CL-1');
  });

  it('shows what went wrong when the core cannot be reached', async () => {
    const page = await render({
      claims: () => throwError(() => new ApiError(0, 'No hay conexión con el sistema central.')),
    });

    expect(page.querySelector('[role=alert]')?.textContent).toContain('No hay conexión');
  });
});
