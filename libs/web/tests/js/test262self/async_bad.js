/*---
description: an async test that fails
flags: [async]
---*/
Promise.resolve(1).then(function (v) { assert.sameValue(v, 2); }).then($DONE, $DONE);
