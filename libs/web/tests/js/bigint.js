// BigInt: literals, arithmetic, comparisons, conversions, the builtins and typed arrays. What it logs was
// checked against Node.js (V8).
const big = 2n ** 128n - 1n;
console.log(String(big), big.toString(16), big.toString(36));
console.log(typeof 1n, 0x1fn, 0o17n, 0b101n, 1_000_000n);
console.log(-7n / 2n, -7n % 2n, 7n % -2n, (-2n) ** 3n);
console.log(1n << 70n, -1n >> 3n, 255n & -16n, 5n | -8n, 6n ^ 3n, ~41n);
console.log(1n == 1, 1n === 1, 2n > 1.5, "10" == 10n, 9007199254740993n > 9007199254740992);
console.log(BigInt.asIntN(8, 255n), BigInt.asUintN(8, -1n), BigInt.asIntN(64, 2n ** 63n));
console.log(BigInt("  0x10  "), BigInt(true), BigInt(Number.MAX_SAFE_INTEGER) + 2n);
console.log(Number(2n ** 64n), Number(-(2n ** 1023n) * 2n), parseInt("12n"));
let x = 10n; x++; x += 5n; x *= -1n;
console.log(x, -x, x ? "truthy" : "falsy", 0n ? "truthy" : "falsy");
for (const bad of [() => 1n + 1, () => +1n, () => 1n >>> 0n, () => 1n / 0n, () => BigInt(1.5), () => BigInt("1.5"), () => JSON.stringify({ a: 1n })]) {
  try { bad(); console.log("no error"); } catch (e) { console.log(e.constructor.name); }
}
const m = new Map([[3n, "three"]]);
console.log(m.get(3n), new Set([1n, 1n, 2n]).size, [1n, 2n].includes(2n), Object.is(0n, -0n));
const a = new BigInt64Array([1n, -2n, 2n ** 63n]);
const u = new BigUint64Array(2);
u[0] = -1n;
console.log(a[0], a[1], a[2], u[0], a.length, BigInt64Array.BYTES_PER_ELEMENT);
console.log(new BigInt64Array([5n, -3n, 10n]).sort().join());
const view = new DataView(new ArrayBuffer(8));
view.setBigUint64(0, 0x0102030405060708n);
console.log(view.getUint8(0), view.getBigInt64(0, true));
try { a[0] = 1; } catch (e) { console.log(e.constructor.name); }
console.log(`${10n ** 20n}`, Object.prototype.toString.call(1n), (123n).toLocaleString());
