import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiError, CoreApi } from '../api/core-api';
import { ClaimStatus, ClaimSummary } from '../api/models';
import { coverageLabel, statusLabel } from '../labels';

const QUEUES: { label: string; statuses: ClaimStatus[] }[] = [
  { label: 'Por revisar', statuses: ['PENDING_REVIEW', 'UNDER_INVESTIGATION'] },
  { label: 'En investigación', statuses: ['UNDER_INVESTIGATION'] },
  { label: 'Esperando documentos', statuses: ['WAITING_DOCUMENTS'] },
  { label: 'Cerrados', statuses: ['PAID', 'REJECTED'] },
];

/** The claims handler's inbox: claims waiting for a person, oldest incident first. */
@Component({
  selector: 'app-inbox',
  imports: [RouterLink],
  templateUrl: './inbox.html',
})
export class Inbox {
  private readonly api = inject(CoreApi);

  protected readonly queues = QUEUES;
  protected readonly queue = signal(0);
  protected readonly claims = signal<ClaimSummary[] | null>(null);
  protected readonly error = signal('');
  protected readonly filter = signal('');
  protected readonly shown = computed(() => {
    const text = this.filter().trim().toUpperCase();
    const all = this.claims() ?? [];
    return text
      ? all.filter((c) => c.claim_id.includes(text) || c.policy_number.includes(text))
      : all;
  });
  protected readonly statusLabel = statusLabel;
  protected readonly coverageLabel = coverageLabel;

  constructor() {
    this.load(0);
  }

  load(index: number): void {
    this.queue.set(index);
    this.claims.set(null);
    this.error.set('');
    this.api.claims(QUEUES[index].statuses).subscribe({
      next: (claims) =>
        this.claims.set([...claims].sort((a, b) => a.incident_date.localeCompare(b.incident_date))),
      error: (e: ApiError) => this.error.set(e.message),
    });
  }
}
