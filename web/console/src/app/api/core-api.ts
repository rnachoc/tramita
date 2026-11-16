import { HttpClient, HttpErrorResponse, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, of, shareReplay, throwError } from 'rxjs';

import {
  AuditEvent,
  Claim,
  ClaimStatus,
  ClaimSummary,
  Clause,
  ReviewRecorded,
  ReviewRequest,
} from './models';

/**
 * The core API as the console sees it. Requests go to /api on the console's own origin; the
 * proxy in front of the console adds the REVIEWER key, so the browser never holds it.
 */
@Injectable({ providedIn: 'root' })
export class CoreApi {
  private readonly http = inject(HttpClient);
  private clauses$?: Observable<Map<string, Clause>>;

  claims(statuses: ClaimStatus[]): Observable<ClaimSummary[]> {
    let params = new HttpParams();
    for (const status of statuses) {
      params = params.append('status', status);
    }
    return this.http.get<ClaimSummary[]>('/api/claims', { params }).pipe(catchError(problem));
  }

  claim(id: string): Observable<Claim> {
    return this.http.get<Claim>(`/api/claims/${encodeURIComponent(id)}`).pipe(catchError(problem));
  }

  audit(id: string): Observable<AuditEvent[]> {
    return this.http
      .get<AuditEvent[]>(`/api/claims/${encodeURIComponent(id)}/audit`)
      .pipe(catchError(problem));
  }

  /** Records a review. The idempotency key makes a retried click count once. */
  review(id: string, request: ReviewRequest, idempotencyKey: string): Observable<ReviewRecorded> {
    const headers = new HttpHeaders({ 'Idempotency-Key': idempotencyKey });
    return this.http
      .post<ReviewRecorded>(`/api/claims/${encodeURIComponent(id)}/reviews`, request, { headers })
      .pipe(catchError(problem));
  }

  /** The policy conditions, clause by clause (the same file the rules cite), loaded once. */
  clauses(): Observable<Map<string, Clause>> {
    this.clauses$ ??= this.http.get<Clause[]>('/clauses.json').pipe(
      map((list) => new Map(list.map((c) => [c.clause_id, c]))),
      catchError(() => of(new Map<string, Clause>())),
      shareReplay(1),
    );
    return this.clauses$;
  }
}

/** An error the console can show: the core's problem detail names the field to fix. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function problem(error: HttpErrorResponse): Observable<never> {
  const body = error.error as { detail?: string; title?: string } | null;
  const message =
    body?.detail ??
    body?.title ??
    (error.status === 0 ? 'No hay conexión con el sistema central.' : error.message);
  return throwError(() => new ApiError(error.status, message));
}
