# on-call notes

- 2026-10-06: moved nightly from 2 to 3 workers (third CPU box freed up). Same code.
- 2026-10-07: nightly died at end of epoch 0. gloo "enforce fail ... pair.cc" / "Connection reset by peer".
  Looks like networking between the workers? Tried eth0 vs lo and lazy init, no change.
- 2026-10-08: someone saw it hang instead of crash with a different N_TRAIN. Raised GLOO_TIMEOUT_S to 1800.
- TODO: is gloo just flaky with 3 ranks? Go back to 2?
