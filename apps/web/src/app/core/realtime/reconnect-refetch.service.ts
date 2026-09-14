import { Injectable, inject } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { Observable } from 'rxjs';
import { filter, map, pairwise } from 'rxjs/operators';
import { RealtimeService } from './ably.service';

/** 斷線重連強制覆蓋（FR-021~025，research.md #8）——供計分板/控制板
 * （單一場地、全部場地）/管理頁場地控制區塊共用，避免四處各自重複實作
 * 同一段「連線狀態轉換」判斷。 */
@Injectable({ providedIn: 'root' })
export class ReconnectRefetchService {
  private readonly realtime = inject(RealtimeService);

  /** `toObservable()` MUST run inside an injection context — building it
   * once here, during this service's own construction (itself always
   * injection-context-safe, since Angular's DI is what constructs this
   * class), means `onReconnect()` below stays safe to call from anywhere,
   * including from *inside* another service's method invoked from a
   * reactive `effect()` callback (`NotificationService.init()`, called
   * from `nav-shell`'s login-state effect) — that call site is NOT itself
   * an injection context, which is exactly what previously threw NG0203
   * ("must be called in an injection context") there. */
  private readonly reconnected$: Observable<void> = toObservable(
    this.realtime.connectionState,
  ).pipe(
    pairwise(),
    filter(([previous, current]) => previous !== 'connected' && current === 'connected'),
    map(() => undefined),
  );

  /** 僅在連線狀態從「非 connected」轉為「connected」時觸發一次（即真正
   * 的斷線後重連，MUST NOT 包含初次連線）——呼叫端應在收到此事件時強制
   * 重新拉取完整狀態並覆蓋畫面，MUST NOT 信任重連前的本地暫存內容。 */
  onReconnect(): Observable<void> {
    return this.reconnected$;
  }
}
