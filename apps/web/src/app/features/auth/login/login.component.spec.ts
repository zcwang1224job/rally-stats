import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { AuthService } from '../auth.service';
import { LoginComponent } from './login.component';

const REMEMBERED_EMAIL_KEY = 'rally-stats:remembered-login-email';

@Component({ selector: 'app-stub-member', template: '' })
class StubMemberComponent {}

describe('LoginComponent', () => {
  function setup(auth: Partial<AuthService> = { login: () => of({}) as never }) {
    TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideRouter([{ path: 'member', component: StubMemberComponent }]),
        provideTranslateService({}),
        { provide: AuthService, useValue: auth },
      ],
    });
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => {
    localStorage.clear();
  });

  it('no remembered email: the form starts blank with the checkbox unchecked, and focus is left alone', () => {
    const fixture = setup();

    expect(fixture.componentInstance.form.controls.email.value).toBe('');
    expect(fixture.componentInstance.form.controls.rememberEmail.value).toBe(false);
    expect(document.activeElement?.getAttribute('formcontrolname')).not.toBe('password');
  });

  it('a remembered email: prefills the field, checks the box, and moves focus straight to the password field', () => {
    localStorage.setItem(REMEMBERED_EMAIL_KEY, 'a@example.com');

    const fixture = setup();

    expect(fixture.componentInstance.form.controls.email.value).toBe('a@example.com');
    expect(fixture.componentInstance.form.controls.rememberEmail.value).toBe(true);
    expect(document.activeElement).toBe(fixture.componentInstance.passwordInput()?.nativeElement);
  });

  it('submitting with the box checked stores the email for next time', () => {
    const fixture = setup();
    fixture.componentInstance.form.setValue({
      email: 'b@example.com',
      password: 'abc12345',
      rememberEmail: true,
    });

    fixture.componentInstance.submit();

    expect(localStorage.getItem(REMEMBERED_EMAIL_KEY)).toBe('b@example.com');
  });

  it('submitting with the box unchecked clears any previously remembered email', () => {
    localStorage.setItem(REMEMBERED_EMAIL_KEY, 'old@example.com');
    const fixture = setup();
    fixture.componentInstance.form.setValue({
      email: 'old@example.com',
      password: 'abc12345',
      rememberEmail: false,
    });

    fixture.componentInstance.submit();

    expect(localStorage.getItem(REMEMBERED_EMAIL_KEY)).toBeNull();
  });
});
