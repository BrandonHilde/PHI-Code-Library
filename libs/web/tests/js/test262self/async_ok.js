/*---
description: an async test that finishes
flags: [async]
---*/
Promise.resolve(1).then(function (v) { assert.sameValue(v, 1); }).then($DONE, $DONE);
