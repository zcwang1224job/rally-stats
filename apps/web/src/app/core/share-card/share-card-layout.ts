/** 041-group-share-cards research.md Decision 6: the middle of every card
 * (between its header and footer) is a stack of blocks. */

// Where the middle of a card may draw (research.md Decision 6). The promo
// footer is 240 tall with a 56px bottom margin, so it starts at
// 1350 − 56 − 240 = 1054; its divider sits 28 above that (1026), and the
// middle keeps 30 clear of the divider (996). The header ends by y = 166,
// so the middle may start at 210 — 786px in all.
export const SHARE_CARD_FOOTER_TOP = 1054;
export const SHARE_CARD_MIDDLE_TOP = 210;
export const SHARE_CARD_MIDDLE_BOTTOM = 996;
export const SHARE_CARD_BLOCK_GAP = 48;
export const SHARE_CARD_BLOCK_MIN_GAP = 32;

export interface Block {
  height: number;
  /** How far the block may shrink when the stack doesn't fit; without it
   * the block is never shrunk. */
  minHeight?: number;
  draw(y: number, height: number): void;
}

export interface StackArea {
  top: number;
  bottom: number;
  gap: number;
  minGap: number;
}

/** Stacks `blocks` between `top` and `bottom`, in whole pixels:
 * 1. they fit with the full gap → centered, nothing shrunk (040's layout);
 * 2. else the gap narrows just enough, down to `minGap`, blocks untouched;
 * 3. else blocks with a `minHeight` shrink, top-down, each only as far as
 *    still needed — the stack then starts at `top`;
 * 4. if even that isn't enough, it simply runs on from `top`. */
export function stackBlocks(blocks: readonly Block[], area: StackArea): void {
  if (blocks.length === 0) {
    return;
  }
  const available = area.bottom - area.top;
  const gaps = blocks.length - 1;
  const heights = blocks.map((block) => block.height);
  const total = heights.reduce((sum, height) => sum + height, 0);

  let gap = area.gap;
  let start: number;
  if (total + gap * gaps <= available) {
    start = area.top + Math.floor((available - total - gap * gaps) / 2);
  } else {
    gap = gaps > 0 ? Math.max(area.minGap, Math.floor((available - total) / gaps)) : 0;
    const needed = total + gap * gaps;
    if (needed <= available) {
      start = area.top + Math.floor((available - needed) / 2);
    } else {
      let over = needed - available;
      blocks.forEach((block, index) => {
        if (over <= 0 || block.minHeight === undefined) {
          return;
        }
        const cut = Math.min(over, Math.max(0, heights[index] - block.minHeight));
        heights[index] -= cut;
        over -= cut;
      });
      start = area.top;
    }
  }

  let y = start;
  blocks.forEach((block, index) => {
    block.draw(y, heights[index]);
    y += heights[index] + gap;
  });
}
