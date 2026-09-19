import { Component, input } from '@angular/core';

export type IconName =
  | 'menu'
  | 'clock'
  | 'lock'
  | 'unlock'
  | 'user'
  | 'map-pin'
  | 'swap'
  | 'grip'
  | 'plus'
  | 'x'
  | 'phone'
  | 'monitor'
  | 'help';

/** The app's UI icon set: 24×24 line icons at 1em, stroked in the current
 * text color, so they size and color with the label next to them and look
 * the same on every OS (unlike emoji). Decorative — always pair with text
 * or an aria-label on the control; the icon itself is hidden from AT. */
@Component({
  selector: 'app-icon',
  template: `
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      @switch (name()) {
        @case ('menu') {
          <path d="M4 6h16M4 12h16M4 18h16" />
        }
        @case ('clock') {
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        }
        @case ('lock') {
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path d="M8 11V7a4 4 0 0 1 8 0v4" />
        }
        @case ('unlock') {
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path d="M8 11V7a4 4 0 0 1 7.5-2" />
        }
        @case ('user') {
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21a8 8 0 0 1 16 0" />
        }
        @case ('map-pin') {
          <path d="M12 21s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z" />
          <circle cx="12" cy="9" r="2.5" />
        }
        @case ('swap') {
          <path d="M4 7h16M16 3l4 4-4 4M20 17H4M8 13l-4 4 4 4" />
        }
        @case ('grip') {
          <circle cx="9" cy="6" r="1" />
          <circle cx="15" cy="6" r="1" />
          <circle cx="9" cy="12" r="1" />
          <circle cx="15" cy="12" r="1" />
          <circle cx="9" cy="18" r="1" />
          <circle cx="15" cy="18" r="1" />
        }
        @case ('plus') {
          <path d="M12 5v14M5 12h14" />
        }
        @case ('x') {
          <path d="M6 6l12 12M18 6L6 18" />
        }
        @case ('phone') {
          <rect x="7" y="2" width="10" height="20" rx="2" />
          <path d="M11 18h2" />
        }
        @case ('monitor') {
          <rect x="3" y="4" width="18" height="12" rx="2" />
          <path d="M8 20h8M12 16v4" />
        }
        @case ('help') {
          <circle cx="12" cy="12" r="9" />
          <path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01" />
        }
      }
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      flex-shrink: 0;
      width: 1em;
      height: 1em;
      vertical-align: -0.125em;
    }

    svg {
      width: 100%;
      height: 100%;
    }
  `,
})
export class IconComponent {
  readonly name = input.required<IconName>();
}
