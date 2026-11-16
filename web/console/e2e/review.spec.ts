import { APIRequestContext, expect, Page, test } from '@playwright/test';

/** A claim waiting for review whose evaluation pays something, found through the console proxy. */
async function pendingPayment(request: APIRequestContext): Promise<{ id: string; amount: number }> {
  const inbox = await request.get('/api/claims?status=PENDING_REVIEW');
  expect(inbox.ok()).toBeTruthy();
  for (const summary of (await inbox.json()) as { claim_id: string }[]) {
    const claim = await (await request.get(`/api/claims/${summary.claim_id}`)).json();
    const latest = claim.proposals.at(-1);
    if (latest?.decision === 'APPROVE' && latest.payable_amount > 0) {
      return { id: summary.claim_id, amount: latest.payable_amount };
    }
  }
  throw new Error('no claim with a payment waiting for review');
}

/** Fails the test on any console error or Content-Security-Policy violation. */
function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(e.message));
  return errors;
}

test('a claims handler approves a payment and the claim is paid', async ({ page, request }) => {
  const errors = watchErrors(page);
  const sentKeys: string[] = [];
  page.on('request', (r) => {
    const key = r.headers()['x-api-key'];
    if (key) sentKeys.push(key);
  });
  const { id } = await pendingPayment(request);

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Bandeja de siniestros' })).toBeVisible();
  await page.getByPlaceholder('Buscar por siniestro o póliza').fill(id);
  await page.getByRole('link', { name: id }).click();

  await expect(page.getByRole('heading', { name: `Siniestro ${id}` })).toBeVisible();
  await expect(page.getByTestId('evaluation')).toContainText('Aprobar');
  await expect(page.getByTestId('claim-status')).toHaveText('Pendiente de revisión');

  const review = page.getByTestId('review');
  await review.getByLabel('Tu nombre').fill('Tramitadora de pruebas');
  await review.getByLabel('Aprobar la evaluación').check();
  await review.getByRole('button', { name: 'Registrar revisión' }).click();

  await expect(page.getByTestId('outcome')).toContainText('Revisión registrada: Pagado');
  await expect(page.getByTestId('claim-status')).toHaveText('Pagado');
  await expect(page.getByText('REVIEW_RECORDED')).toBeVisible();
  await expect(page.getByText('PAYMENT_EXECUTED')).toBeVisible();

  expect(sentKeys, 'the browser must never send an API key').toEqual([]);
  expect(errors).toEqual([]);
});

test('a rejection without a comment is refused before it is sent', async ({ page, request }) => {
  const { id } = await pendingPayment(request);
  let reviews = 0;
  page.on('request', (r) => r.method() === 'POST' && reviews++);

  await page.goto(`/claims/${id}`);
  const review = page.getByTestId('review');
  await review.getByLabel('Tu nombre').fill('Tramitadora de pruebas');
  await review.getByLabel('Rechazar').check();
  await review.getByRole('button', { name: 'Registrar revisión' }).click();

  await expect(review.getByRole('alert')).toContainText('Explica la corrección o el rechazo');
  expect(reviews).toBe(0);
});

test('the key is in no file the browser downloads', async ({ page }) => {
  const bodies: string[] = [];
  page.on('response', async (r) => {
    if (/\.(js|css|html|json)$/.test(new URL(r.url()).pathname) || r.url().endsWith('/')) {
      bodies.push(await r.text());
    }
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Bandeja de siniestros' })).toBeVisible();

  const key = process.env['TRAMITA_CONSOLE_API_KEY'] ?? 'console-change-me-local-only';
  expect(bodies.length).toBeGreaterThan(1);
  for (const body of bodies) {
    expect(body).not.toContain(key);
  }
});
