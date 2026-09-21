import { Block, stackBlocks } from './share-card-layout';

type Call = [y: number, height: number];

/** A block that remembers where it was drawn and how tall. */
function block(height: number, minHeight?: number): Block & { calls: Call[] } {
  const calls: Call[] = [];
  return {
    height,
    ...(minHeight === undefined ? {} : { minHeight }),
    calls,
    draw(y, h) {
      calls.push([y, h]);
    },
  };
}

const area = (bottom: number) => ({ top: 0, bottom, gap: 48, minGap: 32 });

describe('stackBlocks (041 research.md Decision 6)', () => {
  it('centers blocks that fit, with the full gap and their own heights', () => {
    const a = block(100);
    const b = block(200);

    stackBlocks([a, b], area(500));

    // 100 + 48 + 200 = 348; 152 left over, half of it above.
    expect(a.calls).toEqual([[76, 100]]);
    expect(b.calls).toEqual([[224, 200]]);
  });

  it('keeps the 040 layout when the card offsets the area', () => {
    const a = block(100);

    stackBlocks([a], { top: 230, bottom: 1174, gap: 48, minGap: 32 });

    expect(a.calls).toEqual([[230 + Math.floor((944 - 100) / 2), 100]]);
  });

  it('first narrows the gap just enough, keeping every block its size', () => {
    const blocks = [block(200, 100), block(200), block(200)];

    stackBlocks(blocks, area(670));

    // 600 of blocks, 70 left for two gaps → 35 each.
    expect(blocks.map((b) => b.calls[0])).toEqual([
      [0, 200],
      [235, 200],
      [470, 200],
    ]);
  });

  it('centers what is left after narrowing, in whole pixels', () => {
    const blocks = [block(200), block(200), block(200)];

    stackBlocks(blocks, area(675));

    // floor(75 / 2) = 37 per gap, 1px left → starts at floor(1 / 2) = 0.
    expect(blocks.map((b) => b.calls[0][0])).toEqual([0, 237, 474]);
  });

  it('then shrinks the first shrinkable block only as far as needed', () => {
    const a = block(200, 100);
    const b = block(200, 150);
    const c = block(200);

    stackBlocks([a, b, c], area(600));

    // 600 + 2 × 32 = 664 → 64 too tall, all taken from the first block.
    expect(a.calls).toEqual([[0, 136]]);
    expect(b.calls).toEqual([[168, 200]]);
    expect(c.calls).toEqual([[400, 200]]);
  });

  it('moves on to the next shrinkable block once the first reaches its minimum', () => {
    const a = block(200, 100);
    const b = block(200, 150);
    const c = block(200);

    stackBlocks([a, b, c], area(520));

    // 144 too tall: 100 from a (down to its minimum), 44 from b.
    expect(a.calls).toEqual([[0, 100]]);
    expect(b.calls).toEqual([[132, 156]]);
    expect(c.calls).toEqual([[320, 200]]);
  });

  it('never shrinks a block without a minimum', () => {
    const a = block(200);
    const b = block(200, 150);

    stackBlocks([a, b], area(400));

    expect(a.calls[0][1]).toBe(200);
    expect(b.calls[0][1]).toBe(168);
  });

  it('stacks from the top when even the minimums do not fit', () => {
    const a = block(200, 100);
    const b = block(200, 150);
    const c = block(200);

    stackBlocks([a, b, c], area(400));

    expect(a.calls).toEqual([[0, 100]]);
    expect(b.calls).toEqual([[132, 150]]);
    expect(c.calls).toEqual([[314, 200]]);
  });

  it('shrinks a single block that is too tall on its own', () => {
    const a = block(300, 200);

    stackBlocks([a], area(250));

    expect(a.calls).toEqual([[0, 250]]);
  });

  it('does nothing with no blocks', () => {
    expect(() => stackBlocks([], area(100))).not.toThrow();
  });

  it('lays out the same blocks the same way every time (SC-010)', () => {
    const run = () => {
      const blocks = [block(200, 100), block(180, 150), block(90)];
      stackBlocks(blocks, area(420));
      return blocks.map((b) => b.calls);
    };

    expect(run()).toEqual(run());
  });
});
