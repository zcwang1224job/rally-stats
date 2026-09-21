import { ShareCardCanvas } from '../share-card-canvas';

export interface RecordedText {
  text: string;
  x: number;
  y: number;
  font: string;
  fillStyle: string;
  textAlign: CanvasTextAlign;
  /** Width `measureText` reports for this text at this font. */
  width: number;
}

/** 041-group-share-cards: one entry per visible mark, in drawing order, with
 * its vertical extent — lets a test measure just the middle of a card. */
export interface RecordedOp {
  kind: 'text' | 'rect' | 'roundRect' | 'arc';
  top: number;
  bottom: number;
}

/** 040-match-share-card research.md Decision 3: jsdom has no canvas, so the
 * renderer is tested against this recorder. `measureText` approximates a
 * glyph by its script (see measureText) — enough to check truncation and bounds. */
export class RecordingContext implements ShareCardCanvas {
  fillStyle: string | CanvasGradient | CanvasPattern = '#000';
  strokeStyle: string | CanvasGradient | CanvasPattern = '#000';
  lineWidth = 1;
  lineJoin: CanvasLineJoin = 'miter';
  font = '10px sans-serif';
  textAlign: CanvasTextAlign = 'start';
  textBaseline: CanvasTextBaseline = 'alphabetic';

  readonly recordedTexts: RecordedText[] = [];
  readonly recordedPolylines: { color: string; points: number }[] = [];
  readonly recordedRects: { x: number; y: number; w: number; h: number; color: string }[] = [];
  readonly recordedRoundRects: { x: number; y: number; w: number; h: number; color: string }[] = [];
  readonly recordedArcs: { x: number; y: number; radius: number; color: string }[] = [];
  readonly ops: RecordedOp[] = [];
  fillCount = 0;

  private currentPathPoints = 0;
  private readonly stack: Pick<RecordingContext, 'font' | 'fillStyle' | 'strokeStyle'>[] = [];

  fontSize(): number {
    const match = /(\d+(?:\.\d+)?)px/.exec(this.font);
    return match ? Number(match[1]) : 10;
  }

  /** A CJK glyph is about 1 em wide, a Latin one about 0.6 em — close
   * enough that a 20-character Chinese nickname really does overflow here
   * the way it would on a phone. */
  measureText(text: string): { width: number } {
    const size = this.fontSize();
    const width = [...text].reduce(
      (sum, char) => sum + (/[\u2E80-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF]/.test(char) ? 1 : 0.6) * size,
      0,
    );
    return { width };
  }

  fillText(text: string, x: number, y: number): void {
    this.recordedTexts.push({
      text,
      x,
      y,
      font: this.font,
      fillStyle: String(this.fillStyle),
      textAlign: this.textAlign,
      width: this.measureText(text).width,
    });
    const size = this.fontSize();
    const top =
      this.textBaseline === 'top' ? y : this.textBaseline === 'middle' ? y - size / 2 : y - size;
    this.ops.push({ kind: 'text', top, bottom: top + size });
  }

  fillRect(x: number, y: number, w: number, h: number): void {
    this.recordedRects.push({ x, y, w, h, color: String(this.fillStyle) });
    this.ops.push({ kind: 'rect', top: y, bottom: y + h });
  }

  beginPath(): void {
    this.currentPathPoints = 0;
  }

  moveTo(): void {
    this.currentPathPoints = 1;
  }

  lineTo(): void {
    this.currentPathPoints += 1;
  }

  stroke(): void {
    if (this.currentPathPoints > 1) {
      this.recordedPolylines.push({
        color: String(this.strokeStyle),
        points: this.currentPathPoints,
      });
    }
  }

  arc(x: number, y: number, radius: number): void {
    this.recordedArcs.push({ x, y, radius, color: String(this.fillStyle) });
    this.ops.push({ kind: 'arc', top: y - radius, bottom: y + radius });
  }

  fill(): void {
    this.fillCount += 1;
  }

  roundRect(x: number, y: number, w: number, h: number): void {
    this.recordedRoundRects.push({ x, y, w, h, color: String(this.fillStyle) });
    this.ops.push({ kind: 'roundRect', top: y, bottom: y + h });
  }

  opCount(): number {
    return this.ops.length;
  }

  /** The lowest edge of the marks between the first `skipFirst` and the
   * last `skipLast` — e.g. skip the full-canvas background and the footer
   * to measure just the middle of a card. */
  bottomEdge({ skipFirst = 0, skipLast = 0 }: { skipFirst?: number; skipLast?: number } = {}): number {
    const slice = this.ops.slice(skipFirst, this.ops.length - skipLast);
    return slice.reduce((max, op) => Math.max(max, op.bottom), -Infinity);
  }

  save(): void {
    this.stack.push({ font: this.font, fillStyle: this.fillStyle, strokeStyle: this.strokeStyle });
  }

  restore(): void {
    const state = this.stack.pop();
    if (state) {
      Object.assign(this, state);
    }
  }

  texts(): string[] {
    return this.recordedTexts.map((t) => t.text);
  }

  findText(substring: string): RecordedText | undefined {
    return this.recordedTexts.find((t) => t.text.includes(substring));
  }

  /** Horizontal extent of a text, whatever its alignment. */
  static span(t: RecordedText): { left: number; right: number } {
    if (t.textAlign === 'right' || t.textAlign === 'end') {
      return { left: t.x - t.width, right: t.x };
    }
    if (t.textAlign === 'center') {
      return { left: t.x - t.width / 2, right: t.x + t.width / 2 };
    }
    return { left: t.x, right: t.x + t.width };
  }
}
