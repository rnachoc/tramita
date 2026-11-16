/** Spanish labels for the codes the core returns. Unknown codes are shown as they come. */

const STATUS: Record<string, string> = {
  RECEIVED: 'Recibido',
  WAITING_DOCUMENTS: 'Esperando documentos',
  PENDING_REVIEW: 'Pendiente de revisión',
  UNDER_INVESTIGATION: 'En investigación',
  APPROVED: 'Aprobado',
  PAID: 'Pagado',
  REJECTED: 'Rechazado',
};

const DECISION: Record<string, string> = {
  APPROVE: 'Aprobar',
  REJECT: 'Rechazar',
  REQUEST_INFO: 'Pedir documentación',
};

const ROUTING: Record<string, string> = {
  AUTO: 'Automático',
  HUMAN_REVIEW: 'Revisión humana',
  FRAUD_INVESTIGATION: 'Investigación de fraude',
};

const COVERAGE: Record<string, string> = {
  HOME_WATER: 'Daños por agua',
  HOME_THEFT: 'Robo en vivienda',
  HOME_GLASS: 'Rotura de cristales',
  AUTO_COLLISION: 'Colisión',
  AUTO_GLASS: 'Lunas',
  AUTO_THEFT: 'Robo de accesorios',
};

const REASON: Record<string, string> = {
  COVERED: 'Cubierto',
  POLICY_NOT_IN_FORCE: 'Póliza no en vigor',
  NOT_INCLUDED: 'Garantía no incluida',
  EXCLUSION: 'Exclusión',
  WAITING_PERIOD: 'Periodo de carencia',
  MISSING_DOCUMENTS: 'Falta documentación',
  ADDITIONAL_INFORMATION: 'Información adicional',
  REVIEW_REQUESTED: 'Revisión pedida por los agentes',
  LATE_NOTICE: 'Comunicado fuera de plazo',
  AMOUNT_ADJUSTED: 'Importe ajustado',
  AMOUNT_RECALCULATED: 'Importe recalculado',
  LIMIT_APPLIED: 'Límite aplicado',
  DEDUCTIBLE_APPLIED: 'Franquicia aplicada',
  ABOVE_REVIEW_THRESHOLD: 'Por encima del umbral de revisión',
  FRAUD_SUSPECTED: 'Sospecha de fraude',
  RULE_VIOLATION: 'Propuesta corregida por las reglas',
};

const label = (table: Record<string, string>) => (code: string | null | undefined) =>
  code ? (table[code] ?? code) : '';

export const statusLabel = label(STATUS);
export const decisionLabel = label(DECISION);
export const routingLabel = label(ROUTING);
export const coverageLabel = label(COVERAGE);
export const reasonLabel = label(REASON);

export const euros = (value: number | null | undefined): string =>
  value === null || value === undefined
    ? '—'
    : new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(value);
