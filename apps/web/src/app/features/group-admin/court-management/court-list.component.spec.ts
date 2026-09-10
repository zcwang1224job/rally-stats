import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { CourtManagementService } from './court-management.service';
import { CourtListResponse } from './court-management.models';
import { CourtListComponent } from './court-list.component';

const listResponse: CourtListResponse = {
  active_court_count: 1,
  courts: [
    {
      court_id: 'c1',
      name: '球場一',
      scoreboard_token: 'sb-tok',
      control_panel_token: 'cp-tok',
      scoreboard_link_version: 0,
      control_panel_link_version: 0,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
};

describe('CourtListComponent (021-group-creation-defaults T017: rename flow)', () => {
  function setup(courtServiceOverrides: Partial<CourtManagementService> = {}) {
    TestBed.configureTestingModule({
      imports: [CourtListComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: CourtManagementService,
          useValue: {
            listCourts: () => of(listResponse),
            ...courtServiceOverrides,
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(CourtListComponent);
    fixture.componentRef.setInput('groupId', 'g1');
    fixture.detectChanges();
    return fixture;
  }

  function renameButton(fixture: ReturnType<typeof setup>): HTMLButtonElement {
    return Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('.court-entry button'),
    ).find((btn) => btn.textContent?.includes('courtManagement.rename'))!;
  }

  it('clicking 重新命名 shows an editable input pre-filled with the current name', () => {
    const fixture = setup();

    renameButton(fixture).click();
    fixture.detectChanges();

    const input: HTMLInputElement = fixture.nativeElement.querySelector(
      '.rename-court-form input[formcontrolname="name"]',
    );
    expect(input).not.toBeNull();
    expect(input.value).toBe('球場一');
  });

  it('submitting a valid new name calls renameCourt() and refreshes the list', () => {
    const renameCourt = vi.fn().mockReturnValue(of({ ...listResponse.courts[0], name: '新場地' }));
    const fixture = setup({
      renameCourt,
      listCourts: vi
        .fn()
        .mockReturnValueOnce(of(listResponse))
        .mockReturnValueOnce(
          of({ active_court_count: 1, courts: [{ ...listResponse.courts[0], name: '新場地' }] }),
        ),
    });

    renameButton(fixture).click();
    fixture.detectChanges();
    fixture.componentInstance.renameForm.controls.name.setValue('新場地');
    fixture.componentInstance.renameCourt(listResponse.courts[0]);
    fixture.detectChanges();

    expect(renameCourt).toHaveBeenCalledWith('g1', 'c1', '新場地');
    expect(fixture.componentInstance.renamingCourtId()).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('新場地');
  });

  it('COURT_NAME_ALREADY_EXISTS shows a clear error and leaves the list unchanged', () => {
    const fixture = setup({
      renameCourt: () =>
        throwError(() => ({
          errorCode: 'COURT_NAME_ALREADY_EXISTS',
          i18nKey: 'errors.COURT_NAME_ALREADY_EXISTS',
          detail: null,
          status: 409,
        })),
    });

    renameButton(fixture).click();
    fixture.detectChanges();
    fixture.componentInstance.renameForm.controls.name.setValue('球場一');
    fixture.componentInstance.renameCourt(listResponse.courts[0]);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('errors.COURT_NAME_ALREADY_EXISTS');
    expect(fixture.componentInstance.courts()[0].name).toBe('球場一');
  });

  it('clicking 取消 does not call any API and restores the original row', () => {
    const renameCourt = vi.fn();
    const fixture = setup({ renameCourt });

    renameButton(fixture).click();
    fixture.detectChanges();
    fixture.componentInstance.renameForm.controls.name.setValue('改一半就放棄');
    fixture.componentInstance.cancelRename();
    fixture.detectChanges();

    expect(renameCourt).not.toHaveBeenCalled();
    expect(fixture.nativeElement.querySelector('.rename-court-form')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('球場一');
  });
});
