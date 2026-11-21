import { twice } from './b.js';
export let counter = 1;
export function bump() { counter = twice(counter); }
export const name = 'modules';
export default function (n) { return 'hello, ' + n; }
console.log('a.js runs (after b.js, which it imports)');
