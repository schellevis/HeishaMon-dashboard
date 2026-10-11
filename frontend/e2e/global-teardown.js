import { down } from './stack.js';

export default async function globalTeardown() {
  await down();
}
