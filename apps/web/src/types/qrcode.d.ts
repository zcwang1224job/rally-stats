/** 041-group-share-cards research.md Decision 4: the share card draws its QR
 * code from `qrcode`'s module matrix, the only part of the package it uses.
 * Declared here instead of adding `@types/qrcode`, so no install step is
 * needed and nothing else of the package leaks into the app's types. */
declare module 'qrcode' {
  export interface QRCodeCreateOptions {
    errorCorrectionLevel?: 'L' | 'M' | 'Q' | 'H';
  }

  export interface QRCodeModules {
    size: number;
    get(row: number, col: number): number | boolean;
  }

  export interface QRCode {
    modules: QRCodeModules;
    version: number;
  }

  export function create(text: string, options?: QRCodeCreateOptions): QRCode;
}
