import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { FriendsService } from '../../features/friends/friends.service';
import { AddFriendButtonComponent } from './add-friend-button.component';

function setup(
  friendshipStatus: 'none' | 'friends' | 'pending_outgoing' | 'pending_incoming',
  inviteEligible: boolean,
  sendResult: unknown = { friend_request_id: 'r1', status: 'pending' },
  options: { iconStyle?: boolean; nickname?: string } = {},
) {
  TestBed.configureTestingModule({
    imports: [AddFriendButtonComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: FriendsService,
        useValue: {
          sendFriendRequestByMemberId: () =>
            sendResult instanceof Error ? throwError(() => sendResult) : of(sendResult),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(AddFriendButtonComponent);
  fixture.componentRef.setInput('memberId', 'm1');
  fixture.componentRef.setInput('friendshipStatus', friendshipStatus);
  fixture.componentRef.setInput('inviteEligible', inviteEligible);
  if (options.iconStyle !== undefined) {
    fixture.componentRef.setInput('iconStyle', options.iconStyle);
  }
  if (options.nickname !== undefined) {
    fixture.componentRef.setInput('nickname', options.nickname);
  }
  fixture.detectChanges();
  return fixture;
}

describe('AddFriendButtonComponent', () => {
  it('none + eligible: renders a clickable button', () => {
    const fixture = setup('none', true);

    const button = fixture.nativeElement.querySelector('button.add-friend-button');
    expect(button).not.toBeNull();
  });

  it('friends: renders the alreadyFriends label, no button', () => {
    const fixture = setup('friends', false);

    expect(fixture.nativeElement.querySelector('button.add-friend-button')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('friends.alreadyFriends');
  });

  it('pending_outgoing: renders the pendingOutgoing label, no button', () => {
    const fixture = setup('pending_outgoing', false);

    expect(fixture.nativeElement.querySelector('button.add-friend-button')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('friends.pendingOutgoing');
  });

  it('pending_incoming: renders the pendingIncoming label, no button', () => {
    const fixture = setup('pending_incoming', false);

    expect(fixture.nativeElement.querySelector('button.add-friend-button')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('friends.pendingIncoming');
  });

  it('none + NOT eligible (target opted out, FR-008): renders nothing at all', () => {
    const fixture = setup('none', false);

    expect(fixture.nativeElement.querySelector('button.add-friend-button')).toBeNull();
    expect(fixture.nativeElement.querySelector('.status-badge')).toBeNull();
    expect(fixture.nativeElement.textContent?.trim()).toBe('');
  });

  it('clicking the button optimistically flips to pending_outgoing on success', () => {
    const fixture = setup('none', true);

    (fixture.nativeElement.querySelector('button.add-friend-button') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('button.add-friend-button')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('friends.pendingOutgoing');
  });

  it('send failure shows an inline alert without changing state', () => {
    const error = Object.assign(new Error('bad'), {
      i18nKey: 'errors.INVITE_VIA_MATCH_PAGES_NOT_ALLOWED',
    });
    const fixture = setup('none', true, error);

    (fixture.nativeElement.querySelector('button.add-friend-button') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('button.add-friend-button')).not.toBeNull();
  });

  // 026-match-record-friend-invite (roster-list redesign): icon variant
  describe('icon style (roster-list usage)', () => {
    it('renders an icon-only button with an svg and no visible text label', () => {
      const fixture = setup('none', true, undefined, { iconStyle: true, nickname: '小明' });

      const button = fixture.nativeElement.querySelector(
        'button.add-friend-button.btn--icon',
      ) as HTMLButtonElement;
      expect(button).not.toBeNull();
      expect(button.querySelector('svg')).not.toBeNull();
      expect(button.textContent?.trim()).toBe('');
    });

    it('includes the nickname in the aria-label', () => {
      const fixture = setup('none', true, undefined, { iconStyle: true, nickname: '小明' });
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', {
        friends: { addFromMatchButtonAriaLabel: '加 {{nickname}} 為好友' },
      });
      translate.use('en');
      fixture.detectChanges();

      const button = fixture.nativeElement.querySelector(
        'button.add-friend-button.btn--icon',
      ) as HTMLButtonElement;
      expect(button.getAttribute('aria-label')).toContain('小明');
    });

    it('still shows the text status label (not an icon) for an existing relationship', () => {
      const fixture = setup('friends', false, undefined, { iconStyle: true, nickname: '小明' });

      expect(fixture.nativeElement.querySelector('button.add-friend-button')).toBeNull();
      expect(fixture.nativeElement.textContent).toContain('friends.alreadyFriends');
    });

    it('clicking the icon button still sends the request', () => {
      const fixture = setup('none', true, undefined, { iconStyle: true, nickname: '小明' });

      (
        fixture.nativeElement.querySelector('button.add-friend-button.btn--icon') as HTMLButtonElement
      ).click();
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('button.add-friend-button')).toBeNull();
      expect(fixture.nativeElement.textContent).toContain('friends.pendingOutgoing');
    });
  });
});
