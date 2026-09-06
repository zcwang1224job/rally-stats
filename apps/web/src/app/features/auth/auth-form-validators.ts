import { AbstractControl, FormGroup, ValidationErrors, ValidatorFn } from '@angular/forms';

/** Mirrors apps/api/app/domains/member/schemas.py's password-strength check
 * (research.md #9: >=8 chars, >=1 letter, >=1 digit) so the same rule
 * applies client-side; the backend remains authoritative. */
export function passwordStrengthValidator(control: AbstractControl): ValidationErrors | null {
  const value = control.value as string | null;
  if (!value) {
    return null;
  }
  const strong = value.length >= 8 && /[A-Za-z]/.test(value) && /\d/.test(value);
  return strong ? null : { passwordTooWeak: true };
}

export function passwordsMatchValidator(
  passwordControlName: string,
  confirmControlName: string,
): ValidatorFn {
  return (group: AbstractControl): ValidationErrors | null => {
    const formGroup = group as FormGroup;
    const password = formGroup.get(passwordControlName)?.value as string | null;
    const confirm = formGroup.get(confirmControlName)?.value as string | null;
    if (!password || !confirm) {
      return null;
    }
    return password === confirm ? null : { passwordMismatch: true };
  };
}
