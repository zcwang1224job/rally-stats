/** 訪客連結尾巴固定帶一個 `openExternalBrowser=1`。
 *
 * 這是 LINE 官方的 query parameter：從 LINE 裡點開的網址只要有它，就會改
 * 用手機預設瀏覽器（iOS Safari／Android Chrome）開啟，而不是 LINE 內建瀏
 * 覽器。訪客連結幾乎都是貼進 LINE 群組的，而內建瀏覽器對這條連結特別不
 * 友善：`/guest-access/:token` 會把 guest session token 寫進瀏覽器儲存空
 * 間，內建瀏覽器的儲存空間跟著聊天視窗走，關掉就沒了，也不能加書籤或加到
 * 主畫面，訪客等於每次都要回聊天室翻連結。
 * https://developers.line.biz/en/docs/line-login/using-line-url-scheme/
 *
 * 複製的連結、QR code、分享到 LINE 都走這裡同一份網址：QR 也可能是用 LINE
 * 內建的掃描器掃的，一樣會落進內建瀏覽器。在 LINE 以外的地方這只是一個沒
 * 人理會的 query string——`GuestAccessComponent` 只讀路徑上的 `:token`。 */
export function guestAccessLink(token: string): string {
  return `${window.location.origin}/guest-access/${token}?openExternalBrowser=1`;
}
