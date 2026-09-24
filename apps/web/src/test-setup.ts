// Vitest setup (spec 043, research Decision 14).
//
// Composition root for the test run: pre-registers sport type modules
// synchronously so hosts render in the same tick, keeping the existing
// synchronous specs (fixture.detectChanges() then query) valid.
export {};
