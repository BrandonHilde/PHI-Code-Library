import { answer } from './b.js';
console.log('c.js (a src module, after the inline one): answer ' + answer + ', element found: ' + (document.getElementById('p') !== null));
