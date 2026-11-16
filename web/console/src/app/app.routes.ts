import { Routes } from '@angular/router';

import { ClaimPage } from './claim/claim-page';
import { Inbox } from './inbox/inbox';

export const routes: Routes = [
  { path: '', component: Inbox, title: 'Bandeja · Tramita' },
  { path: 'claims/:id', component: ClaimPage, title: 'Siniestro · Tramita' },
  { path: '**', redirectTo: '' },
];
