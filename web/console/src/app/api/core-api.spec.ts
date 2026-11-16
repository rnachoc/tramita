import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { ApiError, CoreApi } from './core-api';

describe('CoreApi', () => {
  let api: CoreApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(CoreApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('asks for every status of the queue and never sends a key', async () => {
    const result = firstValueFrom(api.claims(['PENDING_REVIEW', 'UNDER_INVESTIGATION']));
    const request = http.expectOne((r) => r.url === '/api/claims');
    expect(request.request.params.getAll('status')).toEqual([
      'PENDING_REVIEW',
      'UNDER_INVESTIGATION',
    ]);
    expect(request.request.headers.has('X-Api-Key')).toBe(false);
    request.flush([]);
    expect(await result).toEqual([]);
  });

  it('sends a review with its idempotency key', async () => {
    const result = firstValueFrom(
      api.review('CL-1', { reviewer: 'Ana', action: 'APPROVE' }, 'key-1'),
    );
    const request = http.expectOne('/api/claims/CL-1/reviews');
    expect(request.request.method).toBe('POST');
    expect(request.request.headers.get('Idempotency-Key')).toBe('key-1');
    expect(request.request.body).toEqual({ reviewer: 'Ana', action: 'APPROVE' });
    request.flush({ review: {}, claim_status: 'PAID' });
    expect((await result).claim_status).toBe('PAID');
  });

  it('turns the problem detail of the core into a readable error', async () => {
    const result = firstValueFrom(api.claim('CL-9'));
    http
      .expectOne('/api/claims/CL-9')
      .flush(
        { title: 'Not Found', detail: 'Claim CL-9 does not exist' },
        { status: 404, statusText: 'Not Found' },
      );
    await expect(result).rejects.toEqual(new ApiError(404, 'Claim CL-9 does not exist'));
  });

  it('loads the clauses once', async () => {
    const first = firstValueFrom(api.clauses());
    http
      .expectOne('/clauses.json')
      .flush([{ clause_id: 'HP-2.1', product_code: 'HP', title: 'Daños por agua', text: 'x' }]);
    expect((await first).get('HP-2.1')?.title).toBe('Daños por agua');
    expect((await firstValueFrom(api.clauses())).size).toBe(1);
    http.expectNone('/clauses.json');
  });
});
