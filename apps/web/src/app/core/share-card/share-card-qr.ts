import { QrMatrix } from './share-card-option';

/** The white plate the code sits on, in the footer's bottom-right corner. */
export const QR_PLATE_SIZE = 240;
const QUIET_MODULES = 2;
const MIN_MODULE_PX = 4;

/** The one call this app makes into the `qrcode` package — kept to this
 * shape so none of its types leak past this file (research.md Decision 4). */
export type QrCreate = (
  text: string,
  options: { errorCorrectionLevel: 'M' },
) => { modules: { size: number; get(row: number, col: number): number | boolean } };

/** The code's dark/light modules for `url`, or null if the library fails —
 * the card is then made without a code (FR-020). Error correction M: at
 * this URL length it costs no more modules than L. */
export function toQrMatrix(url: string, create: QrCreate): QrMatrix | null {
  try {
    const { modules } = create(url, { errorCorrectionLevel: 'M' });
    return { size: modules.size, isDark: (row, col) => Boolean(modules.get(row, col)) };
  } catch {
    return null;
  }
}

/** research.md Decision 5: the largest EVEN module size that fits the
 * plate with a 2-module quiet zone — even, so a card shrunk to half size
 * (540×675, as chat apps do) still lands every module on whole pixels —
 * and at least 4px. Null when the code has too many modules to draw that
 * big. `offset` centers the modules on the plate. */
export function qrLayout(size: number): { modulePx: number; offset: number } | null {
  const fit = Math.floor(QR_PLATE_SIZE / (size + QUIET_MODULES * 2));
  const modulePx = fit - (fit % 2);
  if (modulePx < MIN_MODULE_PX) {
    return null;
  }
  return { modulePx, offset: Math.floor((QR_PLATE_SIZE - size * modulePx) / 2) };
}
