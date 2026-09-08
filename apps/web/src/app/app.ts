import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter, map, startWith } from 'rxjs';
import { BreadcrumbComponent } from './core/breadcrumb/breadcrumb.component';
import { NavShellComponent } from './core/nav-shell/nav-shell.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, NavShellComponent, BreadcrumbComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  /** Route-driven visibility for the global nav shell (009): defaults to
   * shown; a route (or any of its ancestors) opts out via
   * `data: { navShell: false }` (see app.routes.ts). */
  readonly showNavShell = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      startWith(null),
      map(() => {
        let current = this.route.snapshot;
        while (current.firstChild) {
          current = current.firstChild;
        }
        return current.data['navShell'] !== false;
      }),
    ),
    { initialValue: true },
  );
}
