module github.com/kiff/kiff-guard-cookbook/duplicate-payment-guard/kiff-decide

go 1.23.0

// Module path is github.com/kiffhq/kiff (NOT github.com/kiff/kiff) on
// purpose: this is a VERSION-BOUND module identity, not a stale org name.
// The framework re-declared its module path to github.com/kiff/kiff only
// at v0.4.0; v0.2.0 — the version this recipe's proof was captured against
// — is published under github.com/kiffhq/kiff. Rewriting this to
// github.com/kiff/kiff v0.2.0 does not resolve (path mismatch) and breaks
// the build. Migrating to github.com/kiff/kiff v0.4.0+ is tracked debt: it
// changes the permission model (the current actor/role wiring returns
// permission_denied on v0.4.0) and needs per-recipe re-validation. Do that
// as a dedicated migration, not a find-and-replace.
require github.com/kiffhq/kiff v0.2.0
