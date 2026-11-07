/*---
description: only strict, as the flag says
flags: [onlyStrict]
---*/
assert.sameValue(this, this);
assert.sameValue((function () { return this; })(), undefined);
