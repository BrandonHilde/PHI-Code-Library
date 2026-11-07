# Notes for PHI

What this repo has run into with the PHI compiler, and what we'd ask for. Changes themselves belong in
the PHI repo.

## Requests

1. **An include path or packages for `use`.** `use` only looks next to the file, next to the main program,
   and in the standard library, and it can't go up a folder. So `build.ps1` copies `.philib` files beside
   everything that needs them. PHI's plan still lists packages as open, and this repo would be its first
   real user.
2. **A way to mark what's public in a library.** Everything a library declares is exposed, so helpers need
   prefixes too. PHI's plan says this can come later.
3. **A jump table for a dense `when`.** It matters to image and font decoding as well as to weblib's JS VM.
   It's already on PHI's optimizing list.

## Small problems

**A misleading message when a library doesn't build for a system.** Building a library that uses
`drivers.ata` reports this same text for every system, including 64-bit Windows and Linux:

```
not for 64-bit Windows: libs\mid\cbmid.phi:1:1: error: drivers.ata doesn't work in a 16-bit program (lib/phi/drivers/ata.phi:38: user programs can't use ports; only the kernel can talk to hardware)
```

The reason in brackets is right, but "16-bit program" isn't.
