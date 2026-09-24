import { SHARE_PALETTES } from '../share-card/share-card-palette';
import { testFooter } from '../share-card/testing/footer-ops';
import { RecordingContext } from '../share-card/testing/recording-context';
import { ShareCardContext } from './share-card.models';
import { buildShareCardModel } from './share-card-model';
import { toMatchShareCardOption } from './match-share-card-option';
import { makeDetail } from './testing/detail-fixtures';

const neutral: ShareCardContext = { groupName: '週三羽球團', perspective: { kind: 'neutral' } };

describe('toMatchShareCardOption (041)', () => {
  const model = buildShareCardModel(makeDetail(), neutral);
  const option = toMatchShareCardOption(model);

  it('is tagged card-match and labelled as the match card', () => {
    expect(option.source).toBe('card-match');
    expect(option.labelKey).toBe('matchShareCard.kind');
  });

  it('keeps the model’s file name and alt text', () => {
    expect(option.fileName).toBe(model.fileName);
    expect(option.altText).toEqual(model.altText);
  });

  it('draws the match card', () => {
    const ctx = new RecordingContext();

    option.draw(ctx, {
      palette: SHARE_PALETTES.light,
      text: (key) => key,
      fonts: { base: 'sans-serif', score: 'monospace' },
      footer: testFooter(),
    });

    expect(ctx.texts()).toContain('21');
    expect(ctx.texts()).toContain('17');
    expect(ctx.texts()).toContain('週三羽球團');
  });
});
