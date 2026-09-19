import js from '@eslint/js';
import pluginQuery from '@tanstack/eslint-plugin-query';
import prettier from 'eslint-config-prettier';
import tailwind from 'eslint-plugin-better-tailwindcss';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import { defineConfig, globalIgnores } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig([
  globalIgnores(['dist', 'node_modules']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat['recommended-latest'],
      reactRefresh.configs.vite,
      pluginQuery.configs['flat/recommended'],
    ],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: { 'better-tailwindcss': tailwind },
    settings: { 'better-tailwindcss': { entryPoint: 'src/index.css' } },
    rules: {
      // Tailwind correctness only. Class order and whitespace belong to Prettier.
      // `enforce-canonical-classes` is the same check the Tailwind editor
      // extension underlines (`z-[100]` → `z-100`), so it fails here, not just there.
      'better-tailwindcss/enforce-canonical-classes': 'error',
      'better-tailwindcss/no-unknown-classes': 'error',
      'better-tailwindcss/no-conflicting-classes': 'error',
      'better-tailwindcss/no-duplicate-classes': 'error',
      'better-tailwindcss/no-deprecated-classes': 'error',

      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/consistent-type-definitions': ['error', 'interface'],
      // Event handlers are allowed to be async; React ignores the returned promise.
      '@typescript-eslint/no-misused-promises': [
        'error',
        { checksVoidReturn: { attributes: false } },
      ],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'always', { null: 'ignore' }],
    },
  },
  {
    files: ['*.config.{js,ts}'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
  // Last, so it switches off every formatting rule Prettier owns.
  prettier,
]);
