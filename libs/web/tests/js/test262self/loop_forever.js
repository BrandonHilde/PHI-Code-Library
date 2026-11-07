/*---
description: never ends, and the runner stops it, so this fails rather than hangs
flags: [noStrict]
---*/
while (true) { try { for (;;) {} } catch (e) { } }
