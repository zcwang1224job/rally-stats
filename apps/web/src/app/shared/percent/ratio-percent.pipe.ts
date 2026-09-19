import { Pipe, PipeTransform } from '@angular/core';
import { formatPercent } from '../../core/match-record-detail/ratio-format';

/** `{{ 0.625 | ratioPercent }}` → "63%" — templates' way to the app's one
 * percent rounding (formatPercent). */
@Pipe({ name: 'ratioPercent' })
export class RatioPercentPipe implements PipeTransform {
  transform(ratio: number): string {
    return formatPercent(ratio);
  }
}
