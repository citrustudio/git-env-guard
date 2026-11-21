# Releases

Before enabling releases, check the version and distribution name availability again,
configure the dedicated release App ID as `RELEASE_APP_ID` and its organisation
Actions key secret as `RELEASE_APP_PRIVATE_KEY`. Grant the App only Contents write,
Pull requests write and Metadata read, with no ruleset bypass. Release-please opens
a release PR; required checks and owner approval apply before merge.

Configure a protected `release` environment with owner approval.
Register the PyPI trusted publisher for this repository, `release.yml`, and
that environment. The workflow builds wheel/sdist, attests both, and uses OIDC
trusted publishing, with no long-lived PyPI token.

Do not enable App auto-merge or add it as a bypass actor. The templates cannot
enforce remote rulesets: verify required checks and code-owner approval using the
organisation baseline before the first public push or real release.

Before first public push, review source/fresh-history scans and the exact file
list, bind the public-text workflow to a reviewed public immutable commit, and
verify the organization protections. Private workflow SHAs used for offline
extraction are not public enforcement evidence. Configure the pending publisher
for git-env-guard, release.yml and the protected release environment. Internal
consumers must pin a real release before deleting their current guard or tests.
