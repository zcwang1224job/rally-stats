import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { GroupInviteStatus } from '../../../core/api/group-invite.models';
import {
  NotificationListResponse,
  NotificationSummary,
} from '../../../core/api/notification.models';
import { NotificationService } from '../notification.service';
import { NotificationListComponent } from './notification-list.component';

const friendSummary = {
  member_id: 'm1',
  nickname: '小美',
  user_number: 'aB3dEfGh',
  friend_request_id: null,
};

function groupInviteNotification(status: GroupInviteStatus): NotificationSummary {
  return {
    notification_id: 'n1',
    type: 'group_invite',
    read: false,
    created_at: '2026-09-21T10:00:00Z',
    friend_request: null,
    group_invite: {
      invite_id: 'inv-1',
      group_id: 'g1',
      group_name: '週三團',
      status,
      inviter: { ...friendSummary, nickname: '團長' },
      invitee: friendSummary,
    },
  };
}

describe('NotificationListComponent', () => {
  function setup(notifications: NotificationSummary[]) {
    const response: NotificationListResponse = {
      notifications,
      unread_count: notifications.filter((n) => !n.read).length,
      page: 1,
      total_pages: 1,
    };
    TestBed.configureTestingModule({
      imports: [NotificationListComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: NotificationService,
          useValue: { list: () => of(response), markRead: () => of({}), markAllRead: () => of({}) },
        },
      ],
    });
    const fixture = TestBed.createComponent(NotificationListComponent);
    fixture.detectChanges();
    return fixture;
  }

  function statusBadges(fixture: ReturnType<typeof setup>): string[] {
    return Array.from(
      fixture.nativeElement.querySelectorAll('.notification-item .status-badge'),
    ).map((el) => (el as HTMLElement).textContent?.trim() ?? '');
  }

  it('標示團長已取消的邀請，不必點進去才知道', () => {
    const fixture = setup([groupInviteNotification('cancelled')]);

    expect(statusBadges(fixture)).toContain('groupInvite.status.cancelled');
  });

  it('已拒絕的邀請同樣標示出來', () => {
    expect(statusBadges(setup([groupInviteNotification('declined')]))).toContain(
      'groupInvite.status.declined',
    );
  });

  it('已失效的邀請同樣標示出來', () => {
    expect(statusBadges(setup([groupInviteNotification('invalidated')]))).toContain(
      'groupInvite.status.invalidated',
    );
  });

  it('待回覆的邀請不加狀態標籤——通知文字本身就在說這件事', () => {
    const fixture = setup([groupInviteNotification('pending')]);

    // 只剩「未讀」那顆既有的徽章。
    expect(statusBadges(fixture)).toEqual(['notifications.list.unreadBadge']);
  });

  it('一般好友邀請不受影響', () => {
    const fixture = setup([
      {
        notification_id: 'n2',
        type: 'friend_request',
        read: true,
        created_at: '2026-09-21T10:00:00Z',
        friend_request: { friend_request_id: 'fr1', status: 'pending', requester: friendSummary },
        group_invite: null,
      },
    ]);

    expect(statusBadges(fixture)).toEqual(['notifications.list.readBadge']);
    expect(fixture.nativeElement.textContent).toContain('notifications.list.friendRequestBody');
  });
});
