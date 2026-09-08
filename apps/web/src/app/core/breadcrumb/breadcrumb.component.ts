import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { filter, map, startWith } from 'rxjs';
import { BREADCRUMB_MAP, BreadcrumbCrumb } from './breadcrumb.config';

/** Renders the current page's trail from `BREADCRUMB_MAP`. Routes are flat
 * (see breadcrumb.config.ts), so "current route" is derived the same way
 * `App.showNavShell` does it (app.ts) — walk `route.snapshot` to the
 * matched leaf and read its `routeConfig.path`, which is exactly the key
 * used in the map. */
@Component({
  selector: 'app-breadcrumb',
  imports: [RouterLink, TranslatePipe],
  templateUrl: './breadcrumb.component.html',
  styleUrl: './breadcrumb.component.scss',
})
export class BreadcrumbComponent {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly crumbs = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      startWith(null),
      map((): BreadcrumbCrumb[] => {
        let current = this.route.snapshot;
        while (current.firstChild) {
          current = current.firstChild;
        }
        const path = current.routeConfig?.path;
        return (path !== undefined && BREADCRUMB_MAP[path]) || [];
      }),
    ),
    { requireSync: true },
  );
}
