/** LINE 官方的分享 URL scheme：手機上會喚起 LINE App、桌機則開 LINE 網頁
 * 版，兩邊都是先跳出聊天室選擇器、再把這段文字送出去。它只吃純文字，沒有
 * 「標題＋連結」這種欄位，所以要分享的連結得直接寫進訊息內容裡。
 *
 * 這裡不用 `navigator.share`：那個在桌機瀏覽器多半沒有、手機上也只是跳出
 * 系統分享選單讓人再挑一次 LINE，而開團現場的團長要的是「按一下就進到
 * LINE 選聊天室」。 */
const LINE_SHARE_BASE = 'https://line.me/R/share';

export function buildLineShareUrl(message: string): string {
  return `${LINE_SHARE_BASE}?text=${encodeURIComponent(message)}`;
}
