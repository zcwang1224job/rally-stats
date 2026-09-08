import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { FriendsService } from '../friends.service';
import { FriendListComponent } from './friend-list.component';

const friend = {
  member_id: 'm1',
  nickname: '小美',
  user_number: 'ab12cd34',
  friend_request_id: 'fr1',
};

function setup(totalPages: number, unfriendSpy: () => void = () => undefined) {
  TestBed.configureTestingModule({
    imports: [FriendListComponent],
    providers: [
      provideRouter([]),
      provideTranslateService({}),
      {
        provide: FriendsService,
        useValue: {
          listFriends: () => of({ friends: [friend], page: 1, total_pages: totalPages }),
          unfriend: () => {
            unfriendSpy();
            return of({ friend_request_id: 'fr1', status: 'unfriended' });
          },
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(FriendListComponent);
  fixture.detectChanges();
  return fixture;
}

describe('FriendListComponent', () => {
  it('shows an error instead of a stuck loading spinner when the initial fetch fails', () => {
    TestBed.configureTestingModule({
      imports: [FriendListComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: FriendsService,
          useValue: {
            listFriends: () =>
              throwError(() => ({ errorCode: 'SOMETHING', i18nKey: 'errors.SOMETHING' })),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(FriendListComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance.loading()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('errors.SOMETHING');
  });

  it('renders each friend with nickname, user number, and an unfriend button', () => {
    const fixture = setup(1);

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('小美');
    expect(text).toContain('ab12cd34');
    expect(fixture.nativeElement.querySelector('.friend-list button')).not.toBeNull();
  });

  it('renders pagination when totalPages > 1', () => {
    const fixture = setup(2);

    expect(fixture.nativeElement.querySelector('.pagination')).not.toBeNull();
  });

  it('unfriending calls FriendsService.unfriend with the friend_request_id, not member_id', () => {
    let calledWith: string | undefined;
    TestBed.configureTestingModule({
      imports: [FriendListComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: FriendsService,
          useValue: {
            listFriends: () => of({ friends: [friend], page: 1, total_pages: 1 }),
            unfriend: (id: string) => {
              calledWith = id;
              return of({ friend_request_id: id, status: 'unfriended' });
            },
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(FriendListComponent);
    fixture.detectChanges();

    fixture.componentInstance.openUnfriendDialog(friend);
    fixture.componentInstance.confirmUnfriend();

    expect(calledWith).toBe('fr1');
  });
});
