import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { RegisterResponse } from '../../../core/api/member-auth.models';
import { AuthService } from '../auth.service';
import { RegisterComponent } from './register.component';

/** Deliberately never calls `fixture.detectChanges()` — the template embeds
 * the real `TurnstileWidgetComponent`, which loads an external Cloudflare
 * script from `ngAfterViewInit()` (unwanted/unavailable in a unit test).
 * `submit()`'s payload-construction logic is exercised directly at the
 * component-instance level instead. */
function setup(registerReturn: () => unknown = () => of({} as RegisterResponse)) {
  const registerCalls: unknown[] = [];
  const authServiceStub = {
    register: (payload: unknown) => {
      registerCalls.push(payload);
      return registerReturn();
    },
  };

  TestBed.configureTestingModule({
    imports: [RegisterComponent],
    providers: [
      provideTranslateService({ lang: 'zh-TW' }),
      { provide: AuthService, useValue: authServiceStub },
    ],
  });

  const fixture = TestBed.createComponent(RegisterComponent);
  const component = fixture.componentInstance;
  component.form.setValue({
    email: 'new@example.com',
    password: 'abc12345',
    confirm_password: 'abc12345',
  });
  component.onTurnstileVerified('turnstile-token');

  return { component, registerCalls };
}

describe('RegisterComponent', () => {
  // 024-add-english-language FR-009
  it('submit() includes the current display language in the register payload', () => {
    const { component, registerCalls } = setup();

    component.submit();

    expect(registerCalls).toEqual([
      {
        email: 'new@example.com',
        password: 'abc12345',
        confirm_password: 'abc12345',
        turnstile_token: 'turnstile-token',
        language: 'zh-TW',
      },
    ]);
  });
});
