import { ShareCardOption } from '../share-card/share-card-option';
import { ShareCardModel } from './share-card.models';
import { renderShareCard } from './share-card-renderer';

/** 041-group-share-cards: the match card as one option of the shared
 * preview. Its QR link is tagged `card-match` (FR-019). */
export function toMatchShareCardOption(model: ShareCardModel): ShareCardOption {
  return {
    source: 'card-match',
    labelKey: 'matchShareCard.kind',
    fileName: model.fileName,
    altText: model.altText,
    draw: (ctx, env) => renderShareCard(ctx, model, env),
  };
}
