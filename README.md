# Disposable publication control feasibility probe

This repository is a disposable test fixture. It is not a DeOS production
repository and contains no production credentials. The `deos-production`
environment is configured with a required reviewer. The workflow publishes an
exact candidate SHA to `refs/heads/production` with an exact expected-old lease.
