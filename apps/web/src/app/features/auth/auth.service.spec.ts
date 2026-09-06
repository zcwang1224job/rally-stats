import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('loggedIn is false when no token is stored', () => {
    const service = TestBed.inject(AuthService);
    expect(service.loggedIn()).toBe(false);
  });

  it('loggedIn becomes true after setTokens (as login()/changePassword() would)', () => {
    const service = TestBed.inject(AuthService);
    service.setTokens('access-1', 'refresh-1');
    expect(service.loggedIn()).toBe(true);
  });

  it('loggedIn becomes false after logout, and tokens are cleared', () => {
    const service = TestBed.inject(AuthService);
    service.setTokens('access-1', 'refresh-1');

    service.logout();

    expect(service.loggedIn()).toBe(false);
    expect(service.getAccessToken()).toBeNull();
    expect(service.getRefreshToken()).toBeNull();
  });

  it('loggedIn reflects a token already present at construction time', () => {
    localStorage.setItem('rally-stats:member-access-token', 'preexisting');

    const service = TestBed.inject(AuthService);

    expect(service.loggedIn()).toBe(true);
  });
});
