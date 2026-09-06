import { AbstractControl, FormGroup, ValidationErrors, ValidatorFn } from '@angular/forms';
import { MatchMode, SchedulingMechanism } from '../group-admin.models';

/** Mirrors apps/api/app/domains/group/schemas.py's field/model validators so
 * the same rules apply client-side (FR-003/004/005/014/020/037 all say "MUST
 * exist in both frontend and backend"); the backend remains authoritative. */

export function minMembersForMode(mode: MatchMode): number {
  return mode === 'singles' ? 2 : 4;
}

export function maxMembersValidator(matchModeControlName: string): ValidatorFn {
  return (group: AbstractControl): ValidationErrors | null => {
    const formGroup = group as FormGroup;
    const maxMembers = formGroup.get('max_members')?.value as number | null;
    const matchMode = formGroup.get(matchModeControlName)?.value as MatchMode | null;
    if (maxMembers == null || matchMode == null) {
      return null;
    }
    const minimum = minMembersForMode(matchMode);
    return maxMembers < minimum ? { maxMembersBelowMinimum: { minimum } } : null;
  };
}

export function activityTimePairValidator(group: AbstractControl): ValidationErrors | null {
  const formGroup = group as FormGroup;
  const start = formGroup.get('activity_time_start')?.value as string | null;
  const end = formGroup.get('activity_time_end')?.value as string | null;
  if (!start && !end) {
    return null;
  }
  if (!start || !end) {
    return { activityTimeIncomplete: true };
  }
  if (start >= end) {
    return { activityTimeOutOfOrder: true };
  }
  return null;
}

/** spec 003 FR-042: fixed_partner/individual_mixed only apply to doubles. */
export function schedulingMechanismMatchModeValidator(
  matchModeControlName: string,
  schedulingMechanismControlName: string,
): ValidatorFn {
  return (group: AbstractControl): ValidationErrors | null => {
    const formGroup = group as FormGroup;
    const matchMode = formGroup.get(matchModeControlName)?.value as MatchMode | null;
    const schedulingMechanism = formGroup.get(schedulingMechanismControlName)
      ?.value as SchedulingMechanism | null;
    if (matchMode !== 'singles' || schedulingMechanism == null) {
      return null;
    }
    const requiresDoubles: SchedulingMechanism[] = ['fixed_partner', 'individual_mixed'];
    return requiresDoubles.includes(schedulingMechanism)
      ? { schedulingMechanismMatchModeConflict: true }
      : null;
  };
}

export function customScoringValidator(group: AbstractControl): ValidationErrors | null {
  const formGroup = group as FormGroup;
  if (formGroup.get('scoring_mode')?.value !== 'custom') {
    return null;
  }
  const target = formGroup.get('custom_target_score')?.value as number | null;
  const deuce = formGroup.get('custom_deuce_threshold')?.value as number | null;
  const cap = formGroup.get('custom_cap_score')?.value as number | null;
  if (target == null || target < 1) {
    return { customScoringInvalid: true };
  }
  if (deuce == null || deuce < 1 || deuce > target) {
    return { customScoringInvalid: true };
  }
  if (cap == null || cap < deuce || cap < target) {
    return { customScoringInvalid: true };
  }
  return null;
}
