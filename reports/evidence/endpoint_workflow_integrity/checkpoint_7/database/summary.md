# Persistence evidence

`after_fixes/reproduction_success/database/persistence_export.json` records SQLite table counts, the canonical run row, and all canonical transition rows for `workflow-4970b9cfda8c`.

The verifier compared the SQLite transition count with the API response, stopped the backend, restarted it against the same temporary stores, and reloaded the same terminal state and transition count before deleting the temporary data directory.
