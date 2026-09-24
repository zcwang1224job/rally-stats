import { ShareCardLink, ShareCardSource } from './share-card-option';

/** 041-group-share-cards contracts/landing-link.md §1: where a card sends the
 * people who see it — the public home page of whichever site made the card,
 * tagged only with the card kind (FR-019). No member, group or match ID
 * ever goes into it (FR-021). */
export function buildShareCardLink(
  location: { origin: string; host: string },
  source: ShareCardSource,
): ShareCardLink {
  return {
    qrUrl: `${location.origin}/?ref=${source}`,
    displayUrl: location.host,
  };
}
