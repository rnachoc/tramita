/** Shapes of the core API (snake_case JSON, see docs/architecture.md). */

export type ClaimStatus =
  | 'RECEIVED'
  | 'WAITING_DOCUMENTS'
  | 'PENDING_REVIEW'
  | 'UNDER_INVESTIGATION'
  | 'APPROVED'
  | 'PAID'
  | 'REJECTED';

export type Decision = 'APPROVE' | 'REJECT' | 'REQUEST_INFO';
export type Routing = 'AUTO' | 'HUMAN_REVIEW' | 'FRAUD_INVESTIGATION';
export type ReviewAction = 'APPROVE' | 'CORRECT' | 'REJECT';

export interface ClaimSummary {
  claim_id: string;
  policy_number: string;
  claim_type: string;
  incident_date: string;
  reported_date: string;
  status: ClaimStatus;
  updated_at: string;
}

export interface Policy {
  policy_number: string;
  product_code: string;
  product_name: string;
  start_date: string;
  end_date: string;
  holder_id: string;
  holder_city: string;
}

export interface ExtractedValue {
  value?: string;
  confidence: number;
  notes: string[];
}

export interface Extraction {
  document_type?: string;
  source?: string;
  provider?: string;
  values?: Record<string, ExtractedValue>;
  needs_review?: string[];
  embedded_instructions?: string[];
  checks?: { name: string; detail: string; passed: boolean }[];
}

export interface ClaimDocument {
  document_id: string;
  document_type: string;
  filename: string;
  received_at: string;
  extracted_at?: string;
  extraction?: Extraction;
}

export interface Violation {
  code: string;
  message: string;
}

export interface FraudSignal {
  type: string;
  evidence: string;
  confidence: number;
  source: 'RULE' | 'MODEL';
}

export interface Proposal {
  proposal_id: string;
  created_at: string;
  proposed_decision: Decision;
  eligible_amount?: number;
  proposed_amount?: number;
  exclusion_code?: string;
  citations: string[];
  rationale: string;
  model_metadata?: Record<string, unknown>;
  decision: Decision;
  payable_amount?: number;
  routing: Routing;
  reasons: string[];
  violations: Violation[];
  fraud_score: number;
  fraud_signals: FraudSignal[];
  missing_documents: string[];
  required_citations: string[];
}

export interface Review {
  review_id: string;
  proposal_id: string;
  reviewer: string;
  action: ReviewAction;
  decision: Decision;
  amount?: number;
  comment?: string;
  created_at: string;
}

export interface Payment {
  payment_id: string;
  amount: number;
  iban_masked: string;
  reference: string;
  triggered_by: string;
  executed_at: string;
}

export interface Claim {
  claim_id: string;
  status: ClaimStatus;
  claim_type: string;
  incident_date: string;
  reported_date: string;
  location: string;
  description: string;
  claimed_amount?: number;
  policy: Policy;
  documents: ClaimDocument[];
  proposals: Proposal[];
  reviews: Review[];
  payment?: Payment;
}

export interface AuditEvent {
  event_id: number;
  occurred_at: string;
  actor: string;
  actor_role: string;
  event_type: string;
  details: Record<string, unknown>;
}

export interface ReviewRequest {
  reviewer: string;
  action: ReviewAction;
  decision?: Decision;
  amount?: number;
  comment?: string;
}

export interface ReviewRecorded {
  review: Review;
  claim_status: ClaimStatus;
  payment?: Payment;
}

export interface Clause {
  clause_id: string;
  product_code: string;
  title: string;
  text: string;
}
