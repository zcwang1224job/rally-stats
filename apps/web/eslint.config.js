// @ts-check
const eslint = require("@eslint/js");
const tseslint = require("typescript-eslint");
const angular = require("angular-eslint");

module.exports = tseslint.config(
  {
    files: ["**/*.ts"],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
      ...tseslint.configs.stylistic,
      ...angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      "@angular-eslint/directive-selector": [
        "error",
        {
          type: "attribute",
          prefix: "app",
          style: "camelCase",
        },
      ],
      "@angular-eslint/component-selector": [
        "error",
        {
          type: "element",
          prefix: "app",
          style: "kebab-case",
        },
      ],
    },
  },
  {
    files: ["**/*.html"],
    extends: [
      ...angular.configs.templateRecommended,
      ...angular.configs.templateAccessibility,
    ],
    rules: {},
  },
  // Sport type plugin boundary (spec 043, constitution XII). Core code and the
  // plugin foundation never import a sport type module; sport type modules
  // never import each other. The only exceptions are the composition roots
  // (src/app/sports/registry.ts's lazy loaders, src/test-setup.ts), which carry
  // an inline disable comment.
  {
    files: [
      "src/app/core/**/*.ts",
      "src/app/features/**/*.ts",
      "src/app/shared/**/*.ts",
    ],
    rules: {
      "no-restricted-imports": ["error", { patterns: ["**/sports/types/**"] }],
      // no-restricted-imports does not look at dynamic import().
      "no-restricted-syntax": [
        "error",
        {
          selector: "ImportExpression[source.value=/sports\\/types\\//]",
          message: "Core code must not load a sport type module (constitution XII).",
        },
      ],
    },
  },
  {
    // The plugin foundation itself, which reaches types/ by shorter paths.
    files: [
      "src/app/sports/*.ts",
      "src/app/sports/section-outlet/**/*.ts",
      "src/app/sports/generic-sections/**/*.ts",
      "src/app/sports/hosts/**/*.ts",
    ],
    rules: {
      "no-restricted-imports": [
        "error",
        { patterns: ["**/sports/types/**", "./types/**", "../types/**"] },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector: "ImportExpression[source.value=/(^|\\/)types\\//]",
          message: "Only the registry's loaders may load a sport type module (constitution XII).",
        },
      ],
    },
  },
  {
    files: ["src/app/sports/types/net-rally/**/*.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { patterns: ["**/sports/types/frames/**", "**/sports/types/generic/**"] },
      ],
    },
  },
  {
    files: ["src/app/sports/types/frames/**/*.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { patterns: ["**/sports/types/net-rally/**", "**/sports/types/generic/**"] },
      ],
    },
  },
  {
    files: ["src/app/sports/types/generic/**/*.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { patterns: ["**/sports/types/net-rally/**", "**/sports/types/frames/**"] },
      ],
    },
  }
);
