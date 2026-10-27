import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const PROJECT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const REPO_DIR = path.resolve(PROJECT_DIR, '..');
export const WORK_DIR = path.join(PROJECT_DIR, 'work');
export const ANALYSES_DIR = path.join(WORK_DIR, 'analyses');
export const BLUEPRINTS_DIR = path.join(WORK_DIR, 'blueprints');
