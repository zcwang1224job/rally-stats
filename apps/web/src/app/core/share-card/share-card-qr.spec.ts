import * as QRCode from 'qrcode';
import { QR_PLATE_SIZE, QrCreate, qrLayout, toQrMatrix } from './share-card-qr';

describe('qrLayout (041 research.md Decision 5, FR-020)', () => {
  it('gives the usual 33-module code 6px modules', () => {
    expect(qrLayout(33)).toEqual({ modulePx: 6, offset: Math.floor((240 - 33 * 6) / 2) });
  });

  it('rounds down to an even size, so a half-size copy stays on whole pixels', () => {
    expect(qrLayout(29)!.modulePx).toBe(6);
    expect(qrLayout(37)!.modulePx).toBe(4);
    expect(qrLayout(53)!.modulePx).toBe(4);
  });

  it('gives up below 4px a module — too small to scan once shrunk', () => {
    expect(qrLayout(57)).toBeNull();
    expect(qrLayout(177)).toBeNull();
  });

  it('always fits the plate with a 2-module quiet zone, centered', () => {
    for (let size = 21; size <= 177; size += 4) {
      const layout = qrLayout(size);
      if (layout === null) {
        continue;
      }
      expect(layout.modulePx % 2, `size ${size}`).toBe(0);
      expect(layout.modulePx).toBeGreaterThanOrEqual(4);
      expect((size + 4) * layout.modulePx).toBeLessThanOrEqual(QR_PLATE_SIZE);
      expect(layout.offset * 2 + size * layout.modulePx).toBeLessThanOrEqual(QR_PLATE_SIZE);
      expect(layout.offset * 2 + size * layout.modulePx).toBeGreaterThanOrEqual(QR_PLATE_SIZE - 1);
    }
  });
});

describe('toQrMatrix (041 research.md Decision 4)', () => {
  it('reads the modules the QR library made, at error correction M', () => {
    const create = vi.fn<QrCreate>(() => ({
      modules: { size: 2, get: (row: number, col: number) => (row === col ? 1 : 0) },
    }));

    const matrix = toQrMatrix('https://rallystats.example/?ref=card-rank', create)!;

    expect(create).toHaveBeenCalledWith('https://rallystats.example/?ref=card-rank', {
      errorCorrectionLevel: 'M',
    });
    expect(matrix.size).toBe(2);
    expect([matrix.isDark(0, 0), matrix.isDark(0, 1), matrix.isDark(1, 1)]).toEqual([true, false, true]);
  });

  it('gives no matrix when the library fails — the card is still made', () => {
    const create: QrCreate = () => {
      throw new Error('too long');
    };

    expect(toQrMatrix('x', create)).toBeNull();
  });

  it('makes the same code for the same link every time, with the real library', () => {
    const url = 'https://rallystats.example/?ref=card-leaderboard'.slice(0, 44);
    const a = toQrMatrix(url, QRCode.create)!;
    const b = toQrMatrix(url, QRCode.create)!;

    expect(a.size).toBe(33);
    for (let row = 0; row < a.size; row++) {
      for (let col = 0; col < a.size; col++) {
        expect(a.isDark(row, col)).toBe(b.isDark(row, col));
      }
    }
  });
});
