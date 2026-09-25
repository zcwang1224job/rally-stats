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

/** 043: "1,2,3" → [1, 2, 3]; null unless every step is a positive whole
 * number and they strictly increase (FR-012). */
export function parseScoreSteps(text: string): number[] | null {
  const parts = text
    .split(/[,，、\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  if (parts.length === 0) {
    return null;
  }
  const steps = parts.map((part) => Number(part));
  if (steps.some((step) => !Number.isInteger(step) || step <= 0)) {
    return null;
  }
  for (let i = 1; i < steps.length; i += 1) {
    if (steps[i] <= steps[i - 1]) {
      return null;
    }
  }
  return steps;
}

/** 043 FR-012: the common parameters of an activity without named presets
 * (only checked while the form shows them — `uses_generic_params`). With a
 * cap every match ends by the cap, so target ≥ win_by only matters without
 * one (mirrors the backend's validate_common_params). */
export function genericScoringValidator(group: AbstractControl): ValidationErrors | null {
  const formGroup = group as FormGroup;
  if (formGroup.get('uses_generic_params')?.value !== true) {
    return null;
  }
  const endMode = formGroup.get('end_mode')?.value as string;
  const target = formGroup.get('target_score')?.value as number | null;
  const winBy = formGroup.get('win_by')?.value as number | null;
  const hasCap = formGroup.get('has_cap')?.value === true;
  const cap = formGroup.get('cap_score')?.value as number | null;
  const steps = parseScoreSteps(String(formGroup.get('score_steps')?.value ?? ''));
  if (steps === null) {
    return { genericScoringInvalid: 'score_steps' };
  }
  // Manual end hides the target and lead, so they are not checked.
  if (endMode !== 'target') {
    return null;
  }
  if (target == null || target < 1) {
    return { genericScoringInvalid: 'target_score' };
  }
  if (winBy == null || winBy < 1) {
    return { genericScoringInvalid: 'win_by' };
  }
  if (endMode === 'target') {
    if (hasCap && (cap == null || cap < target)) {
      return { genericScoringInvalid: 'cap_score' };
    }
    if (!hasCap && target < winBy) {
      return { genericScoringInvalid: 'target_score' };
    }
  }
  return null;
}

export function customScoringValidator(group: AbstractControl): ValidationErrors | null {
  const formGroup = group as FormGroup;
  // 043: an activity without named presets edits the common parameters
  // instead of these three fields.
  if (formGroup.get('scoring_mode')?.value !== 'custom' || formGroup.get('uses_generic_params')?.value === true) {
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
