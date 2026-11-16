import { ClaimDocument } from '../api/models';
import { documentFields, documentLines, reviewProblems } from './claim-page';

describe('reviewProblems', () => {
  it('accepts an approval signed by a reviewer', () => {
    expect(reviewProblems({ reviewer: 'Ana', action: 'APPROVE' })).toEqual([]);
  });

  it('asks for a name, a decision, an amount and a comment to correct', () => {
    expect(reviewProblems({ reviewer: ' ', action: 'CORRECT' })).toEqual([
      'Indica tu nombre para firmar la revisión.',
      'Elige la decisión corregida.',
      'Indica el importe corregido.',
      'Explica la corrección o el rechazo en el comentario.',
    ]);
  });

  it('refuses a negative amount and a rejection without a comment', () => {
    expect(
      reviewProblems({
        reviewer: 'Ana',
        action: 'CORRECT',
        decision: 'APPROVE',
        amount: -1,
        comment: 'x',
      }),
    ).toEqual(['El importe no puede ser negativo.']);
    expect(reviewProblems({ reviewer: 'Ana', action: 'REJECT' })).toEqual([
      'Explica la corrección o el rechazo en el comentario.',
    ]);
  });
});

describe('document facts', () => {
  const doc: ClaimDocument = {
    document_id: 'DOC-1',
    document_type: 'INVOICE',
    filename: 'factura.pdf',
    received_at: '2026-01-01T00:00:00Z',
    extraction: {
      values: {
        total: { value: '121.00', confidence: 0.9, notes: [] },
        issuer_tax_id: { value: 'B12345674', confidence: 0.4, notes: [] },
        'lines[1].description': { value: 'Pintura', confidence: 0.9, notes: [] },
        'lines[0].description': { value: 'Tubería', confidence: 0.9, notes: [] },
        'lines[0].amount': { value: '60.00', confidence: 0.9, notes: [] },
        'lines[1].amount': { value: '40.00', confidence: 0.9, notes: [] },
        customer: { confidence: 0, notes: ['not found'] },
      },
    },
  };

  it('lists the fields read, flagging doubtful ones, without the lines', () => {
    expect(documentFields(doc)).toEqual([
      { name: 'total', value: '121.00', low: false },
      { name: 'issuer_tax_id', value: 'B12345674', low: true },
    ]);
  });

  it('rebuilds the line items in order', () => {
    expect(documentLines(doc)).toEqual([
      { description: 'Tubería', amount: '60.00' },
      { description: 'Pintura', amount: '40.00' },
    ]);
  });
});
