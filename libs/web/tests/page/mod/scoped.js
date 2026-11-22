// imports 'greeting', which the page's import map maps to b.js for modules under mod/
import * as g from 'greeting';
export const keys = Object.keys(g).join(',');
