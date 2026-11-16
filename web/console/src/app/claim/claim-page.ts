import { Component, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ApiError, CoreApi } from '../api/core-api';
import {
  AuditEvent,
  Claim,
  ClaimDocument,
  Clause,
  Decision,
  Proposal,
  ReviewAction,
  ReviewRequest,
} from '../api/models';
import {
  coverageLabel,
  decisionLabel,
  euros,
  reasonLabel,
  routingLabel,
  statusLabel,
} from '../labels';
import { newIdempotencyKey } from '../idempotency';
import { Reviewer } from '../reviewer';

const REVIEWABLE = new Set(['PENDING_REVIEW', 'UNDER_INVESTIGATION']);

/** What a review form must say before it can be sent; mirrors the core's checks. */
export function reviewProblems(request: ReviewRequest): string[] {
  const problems: string[] = [];
  if (!request.reviewer.trim()) {
    problems.push('Indica tu nombre para firmar la revisión.');
  }
  if (request.action === 'CORRECT') {
    if (!request.decision) problems.push('Elige la decisión corregida.');
    if (request.amount === undefined || request.amount === null || Number.isNaN(request.amount)) {
      problems.push('Indica el importe corregido.');
    } else if (request.amount < 0) {
      problems.push('El importe no puede ser negativo.');
    }
  }
  if (request.action !== 'APPROVE' && !request.comment?.trim()) {
    problems.push('Explica la corrección o el rechazo en el comentario.');
  }
  return problems;
}

/** Fields of a document worth showing, without the line items (shown as a table). */
export function documentFields(
  doc: ClaimDocument,
): { name: string; value: string; low: boolean }[] {
  const values = doc.extraction?.values ?? {};
  return Object.entries(values)
    .filter(([name, v]) => !name.startsWith('lines[') && v.value !== undefined)
    .map(([name, v]) => ({ name, value: v.value ?? '', low: v.confidence < 0.6 }));
}

export function documentLines(doc: ClaimDocument): { description: string; amount: string }[] {
  const values = doc.extraction?.values ?? {};
  const lines = new Map<number, { description: string; amount: string }>();
  for (const [name, v] of Object.entries(values)) {
    const match = /^lines\[(\d+)\]\.(description|amount)$/.exec(name);
    if (match && v.value !== undefined) {
      const line = lines.get(+match[1]) ?? { description: '', amount: '' };
      line[match[2] as 'description' | 'amount'] = v.value;
      lines.set(+match[1], line);
    }
  }
  return [...lines.entries()].sort(([a], [b]) => a - b).map(([, line]) => line);
}

@Component({
  selector: 'app-claim-page',
  imports: [RouterLink],
  templateUrl: './claim-page.html',
})
export class ClaimPage {
  private readonly api = inject(CoreApi);
  protected readonly reviewer = inject(Reviewer);

  /** Bound from the route parameter. */
  readonly id = input.required<string>();

  protected readonly claim = signal<Claim | null>(null);
  protected readonly audit = signal<AuditEvent[]>([]);
  protected readonly clauses = signal(new Map<string, Clause>());
  protected readonly error = signal('');

  protected readonly proposal = computed<Proposal | null>(
    () => this.claim()?.proposals.at(-1) ?? null,
  );
  protected readonly reviewable = computed(() => REVIEWABLE.has(this.claim()?.status ?? ''));
  protected readonly reviewRequests = computed(() => {
    const requests = this.proposal()?.model_metadata?.['review_requests'];
    return Array.isArray(requests) ? (requests as string[]) : [];
  });

  // Review form
  protected readonly action = signal<ReviewAction>('APPROVE');
  protected readonly decision = signal<Decision | ''>('');
  protected readonly amount = signal<string>('');
  protected readonly comment = signal('');
  protected readonly sending = signal(false);
  protected readonly formErrors = signal<string[]>([]);
  protected readonly outcome = signal('');
  private idempotencyKey = newIdempotencyKey();

  protected readonly statusLabel = statusLabel;
  protected readonly decisionLabel = decisionLabel;
  protected readonly routingLabel = routingLabel;
  protected readonly reasonLabel = reasonLabel;
  protected readonly coverageLabel = coverageLabel;
  protected readonly euros = euros;
  protected readonly documentFields = documentFields;
  protected readonly documentLines = documentLines;

  ngOnInit(): void {
    this.api.clauses().subscribe((clauses) => this.clauses.set(clauses));
    this.load();
  }

  load(): void {
    this.error.set('');
    forkJoin({ claim: this.api.claim(this.id()), audit: this.api.audit(this.id()) }).subscribe({
      next: ({ claim, audit }) => {
        this.claim.set(claim);
        this.audit.set(audit);
      },
      error: (e: ApiError) => this.error.set(e.message),
    });
  }

  clause(id: string): Clause | undefined {
    return this.clauses().get(id);
  }

  request(): ReviewRequest {
    const request: ReviewRequest = { reviewer: this.reviewer.name(), action: this.action() };
    if (this.action() === 'CORRECT') {
      request.decision = this.decision() || undefined;
      request.amount = this.amount() === '' ? undefined : Number(this.amount().replace(',', '.'));
    }
    if (this.comment().trim()) {
      request.comment = this.comment().trim();
    }
    return request;
  }

  submit(): void {
    const request = this.request();
    const problems = reviewProblems(request);
    this.formErrors.set(problems);
    if (problems.length) return;
    this.sending.set(true);
    this.api.review(this.id(), request, this.idempotencyKey).subscribe({
      next: (recorded) => {
        this.sending.set(false);
        this.idempotencyKey = newIdempotencyKey();
        const paid = recorded.payment ? `, pago de ${euros(recorded.payment.amount)}` : '';
        this.outcome.set(`Revisión registrada: ${statusLabel(recorded.claim_status)}${paid}.`);
        this.load();
      },
      error: (e: ApiError) => {
        this.sending.set(false);
        this.formErrors.set([e.message]);
      },
    });
  }
}
