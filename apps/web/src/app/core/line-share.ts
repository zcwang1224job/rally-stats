/** LINE Social Plugins 的分享端點（LINE it!）：手機上會喚起 LINE App 的聊
 * 天室選擇器，桌機則開 LINE 的分享頁（登入 LINE 網頁版後一樣能挑聊天室）。
 *
 * 不用 `line.me/R/share?text=` 那組 App URL scheme——LINE 官方文件明講它
 * 「不支援 PC 版 LINE（macOS、Windows）」，桌機點下去只會停在 line.me 官
 * 網，團長在電腦上開團時等於沒有這顆按鈕。
 * https://developers.line.biz/en/docs/line-social-plugins/install-guide/using-line-share-buttons/
 *
 * 也不用 `navigator.share`：桌機瀏覽器多半沒有，手機上也只是跳出系統分享
 * 選單讓人再挑一次 LINE。
 *
 * `url` 是必填、`text` 選填，送出去的訊息是「text 後面接 url」，所以訊息
 * 文案裡不要再自己寫一次連結。 */
const LINE_SHARE_BASE = 'https://social-plugins.line.me/lineit/share';

export function buildLineShareUrl(link: string, message: string): string {
  return `${LINE_SHARE_BASE}?url=${encodeURIComponent(link)}&text=${encodeURIComponent(message)}`;
}
