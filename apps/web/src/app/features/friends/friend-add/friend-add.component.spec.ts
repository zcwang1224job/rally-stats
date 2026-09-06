import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { FriendsService } from '../friends.service';
import { FriendAddComponent } from './friend-add.component';

function setup(searchResult: unknown, sendResult: unknown = { friend_request_id: 'r1', status: 'pending' }) {
  TestBed.configureTestingModule({
    imports: [FriendAddComponent],
    providers: [
      provideRouter([]),
      provideTranslateService({}),
      {
        provide: FriendsService,
        useValue: {
          searchMember: () =>
            searchResult instanceof Error ? throwError(() => searchResult) : of(searchResult),
          sendFriendRequest: () => of(sendResult),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(FriendAddComponent);
  fixture.detectChanges();
  return fixture;
}

describe('FriendAddComponent', () => {
  it('none status: shows a send-request button', () => {
    const fixture = setup({
      member_id: 'm1',
      nickname: '小美',
      user_number: 'ab12cd34',
      friendship_status: 'none',
    });
    fixture.componentInstance.form.setValue({ user_number: 'ab12cd34' });
    fixture.componentInstance.search();
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.search-result button');
    expect(button).not.toBeNull();
  });

  it('pending_outgoing status: shows a non-actionable label, no button', () => {
    const fixture = setup({
      member_id: 'm1',
      nickname: '小美',
      user_number: 'ab12cd34',
      friendship_status: 'pending_outgoing',
    });
    fixture.componentInstance.form.setValue({ user_number: 'ab12cd34' });
    fixture.componentInstance.search();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.search-result button')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('friends.pendingOutgoing');
  });

  it('friends status: shows the already-friends label', () => {
    const fixture = setup({
      member_id: 'm1',
      nickname: '小美',
      user_number: 'ab12cd34',
      friendship_status: 'friends',
    });
    fixture.componentInstance.form.setValue({ user_number: 'ab12cd34' });
    fixture.componentInstance.search();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('friends.alreadyFriends');
  });

  it('sending a request from none status flips the local state to pending_outgoing', () => {
    const fixture = setup({
      member_id: 'm1',
      nickname: '小美',
      user_number: 'ab12cd34',
      friendship_status: 'none',
    });
    fixture.componentInstance.form.setValue({ user_number: 'ab12cd34' });
    fixture.componentInstance.search();
    fixture.detectChanges();

    (fixture.nativeElement.querySelector('.search-result button') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(fixture.componentInstance.result()?.friendship_status).toBe('pending_outgoing');
  });

  it('search error (e.g. CANNOT_SEARCH_SELF) shows an inline alert', () => {
    const error = Object.assign(new Error('bad'), { i18nKey: 'errors.CANNOT_SEARCH_SELF' });
    const fixture = setup(error);
    fixture.componentInstance.form.setValue({ user_number: 'ab12cd34' });
    fixture.componentInstance.search();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
  });
});
