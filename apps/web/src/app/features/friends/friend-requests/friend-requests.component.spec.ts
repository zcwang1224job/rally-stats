import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { FriendsService } from '../friends.service';
import { FriendRequestsComponent } from './friend-requests.component';

const request = {
  friend_request_id: 'fr1',
  requester: { member_id: 'm1', nickname: '小明', user_number: 'ab12cd34', friend_request_id: null },
  created_at: '2026-09-02T00:00:00Z',
};

function setup(acceptSpy: (id: string) => void = () => undefined) {
  TestBed.configureTestingModule({
    imports: [FriendRequestsComponent],
    providers: [
      provideRouter([]),
      provideTranslateService({}),
      {
        provide: FriendsService,
        useValue: {
          listIncomingRequests: () => of({ requests: [request] }),
          acceptFriendRequest: (id: string) => {
            acceptSpy(id);
            return of({ friend_request_id: id, status: 'accepted' });
          },
          rejectFriendRequest: (id: string) => of({ friend_request_id: id, status: 'rejected' }),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(FriendRequestsComponent);
  fixture.detectChanges();
  return fixture;
}

describe('FriendRequestsComponent', () => {
  it('renders each incoming request with accept/reject actions', () => {
    const fixture = setup();

    expect(fixture.nativeElement.textContent).toContain('小明');
    const buttons = fixture.nativeElement.querySelectorAll('.actions button');
    expect(buttons.length).toBe(2);
  });

  it('accept calls FriendsService.acceptFriendRequest with the right id', () => {
    let acceptedId: string | undefined;
    const fixture = setup((id) => (acceptedId = id));

    fixture.componentInstance.accept(request);

    expect(acceptedId).toBe('fr1');
  });

  it('shows the empty-state message when there are no incoming requests', () => {
    TestBed.configureTestingModule({
      imports: [FriendRequestsComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: FriendsService,
          useValue: { listIncomingRequests: () => of({ requests: [] }) },
        },
      ],
    });
    const fixture = TestBed.createComponent(FriendRequestsComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('friends.emptyRequests');
  });
});
