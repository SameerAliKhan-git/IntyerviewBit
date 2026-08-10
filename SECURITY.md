# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue.

- Open a [private security advisory](https://github.com/SameerAliKhan-git/IntyerviewBit/security/advisories/new) on this repository.

Please include what you found, how to reproduce it, and the impact you believe it has.
Expect an initial response within 7 days. If the report is accepted, a fix will be
prepared before any public disclosure; if it is declined, you will get an explanation.

## Supported versions

This is a demo project, not a maintained product. Only the `main` branch receives fixes.

## Known operational risks

Anyone deploying this should understand the following before exposing it publicly.

**The service exposes an API key's quota to anonymous users.** It is designed to run with
no end-user authentication, so anyone who can reach it can consume the key's quota. The
application enforces per-IP and global session caps (`MAX_SESSIONS_PER_IP`,
`MAX_CONCURRENT_SESSIONS`, `NEW_SESSIONS_PER_IP_PER_HOUR`, `MAX_SESSION_SECONDS`), which
are per-instance and are a floor, not a ceiling.

What that costs you depends on your key:

- **Free-tier key (no billing account attached)** — the default. Abuse cannot produce a
  bill; the worst case is quota exhaustion and 429s for everyone. The shipped defaults are
  deliberately small (2 concurrent sessions, 10 minutes each) because admitting more
  sessions than free-tier concurrency allows makes all of them fail mid-interview instead
  of serving more people.
- **Key on a project with billing enabled** — abuse becomes a bill. **Configure a GCP
  billing budget alert before making such a deployment public**, and consider raising the
  caps only as far as your budget tolerates.

Quota exhaustion is handled explicitly rather than as a generic error: the server
classifies `RESOURCE_EXHAUSTED`/429 responses and tells the client not to retry, so the
browser stops reconnecting, reports the scores captured so far, and shows the real reason.

**Secrets belong in Secret Manager.** Do not pass `GOOGLE_API_KEY` with
`gcloud run deploy --set-env-vars`; that records the key in your shell history, in Cloud
Build logs, and in the Cloud Run revision spec. Use `--set-secrets`, as `cloudbuild.yaml`
and the Terraform config do.

**Set `SESSION_SECRET` in production.** Session tokens authorize reads of a candidate's
analytics. Without this variable each instance signs with an ephemeral key, so tokens
break across restarts and across instances.

**Session data is in-memory and unencrypted.** Interview scores and speech transcripts
are held in the memory of the instance serving the session and are discarded when the
session expires (default 1 hour idle) or the instance recycles. Nothing is persisted to
disk or to a database. Audio and video are streamed to Google's Gemini API for live
analysis and are not recorded by this application.

**`/debug` is disabled by default.** It is gated behind `ENABLE_DEBUG_ENDPOINT` and
never returns key material. Leave it off in production.

## If you leaked a key

Revoking is the only reliable remedy — removing the file from git history does not help
once the repository has been cloned, forked, or indexed.

1. Revoke the key immediately in [Google AI Studio](https://aistudio.google.com/app/apikey)
   or the GCP console.
2. Issue a replacement and store it in Secret Manager.
3. Purge the file from history (`git filter-repo --path <file> --invert-paths`) and force-push.
4. Enable GitHub secret scanning and push protection on the repository.
