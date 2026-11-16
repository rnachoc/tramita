import { Injectable, signal } from '@angular/core';

const KEY = 'tramita.reviewer';

/**
 * The claims handler's name, sent with every review. It is not an identity: the console
 * authenticates as one REVIEWER client (ADR 0009, ADR 0015). Kept for the browser session only.
 */
@Injectable({ providedIn: 'root' })
export class Reviewer {
  readonly name = signal(read());

  set(name: string): void {
    const trimmed = name.trim();
    this.name.set(trimmed);
    try {
      sessionStorage.setItem(KEY, trimmed);
    } catch {
      // storage can be unavailable (private mode); the name then lasts until reload
    }
  }
}

function read(): string {
  try {
    return sessionStorage.getItem(KEY) ?? '';
  } catch {
    return '';
  }
}
