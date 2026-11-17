import { Component, effect, inject, signal } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

import { Reviewer } from './reviewer';

type Theme = 'dark' | 'light';
const THEME_KEY = 'tramita.theme';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  templateUrl: './app.html',
})
export class App {
  protected readonly reviewer = inject(Reviewer);
  /** Dark by default; the choice is remembered in this browser only. */
  protected readonly theme = signal<Theme>(readTheme());

  constructor() {
    effect(() => {
      const theme = this.theme();
      document.documentElement.dataset['theme'] = theme;
      try {
        localStorage.setItem(THEME_KEY, theme);
      } catch {
        // Storage may be unavailable (private mode); the theme still applies to this page.
      }
    });
  }

  protected toggleTheme(): void {
    this.theme.update((t) => (t === 'dark' ? 'light' : 'dark'));
  }
}

function readTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}
